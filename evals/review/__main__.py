import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from botocore.config import Config
from strands.models.bedrock import BedrockModel

from app.review.agent import ReviewAgent, StrandsReviewAgent
from app.review.agentcore.client import AgentCoreClient
from app.review.policy import BedrockPolicyRetriever
from app.review.worker import MAX_OUTPUT_TOKENS
from evals.review.cases import CASE_SETS, load_cases, select_cases
from evals.review.history import RunHistory
from evals.review.report import render_report
from evals.review.results import REPORTS_DIR, AgentPlacement, load_results, save_results
from evals.review.run import run_cases
from evals.review.scoring import expense_clauses, score_run
from evals.review.settings import ReviewEvalSettings

# the account allows 10 model requests per minute
BEDROCK_CLIENT_CONFIG = Config(read_timeout=120, retries={"max_attempts": 10, "mode": "adaptive"})


def build_agent(
    settings: ReviewEvalSettings, history: RunHistory, through_agentcore: bool = False
) -> ReviewAgent:
    if through_agentcore:
        return AgentCoreClient(settings.review_agent_runtime_arn, history, settings.aws_region)
    return StrandsReviewAgent(
        BedrockModel(
            model_id=settings.review_model_id,
            region_name=settings.aws_region,
            boto_client_config=BEDROCK_CLIENT_CONFIG,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0,
        ),
        settings.review_model_id,
        BedrockPolicyRetriever(settings.policy_kb_id, settings.aws_region),
        history,
        max_turns=settings.review_max_turns,
        max_proposal_attempts=settings.review_max_proposal_attempts,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.review")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--cases", type=int, help="review the first N cases of the set (default: all)"
    )
    source.add_argument(
        "--ids",
        type=lambda value: value.split(","),
        help="review these cases, e.g. D07,D17; a case's process_after case runs before it",
    )
    source.add_argument("--results", type=Path, help="score a saved review-*.json, no model calls")
    parser.add_argument(
        "--set", choices=list(CASE_SETS), default="dev", help="the cases to review (default: dev)"
    )
    parser.add_argument(
        "--agentcore",
        action="store_true",
        help="review through the agent on Bedrock AgentCore Runtime (REVIEW_AGENT_RUNTIME_ARN)",
    )
    args = parser.parse_args(argv)
    if args.cases is not None and args.cases < 1:
        parser.error("--cases must be at least 1")

    if args.results:
        results_path = args.results
        results = load_results(results_path)
        case_set = CASE_SETS[results.case_set]
        cases = load_cases(case_set.path)
    else:
        case_set = CASE_SETS[args.set]
        cases = load_cases(case_set.path)
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        for name in ("app.review", "evals.review"):
            logging.getLogger(name).setLevel(logging.INFO)
        if args.ids:
            try:
                selected_cases = select_cases(cases, args.ids)
            except ValueError as exc:
                parser.error(str(exc))
        else:
            selected_cases = cases[: args.cases]
        settings = ReviewEvalSettings()
        if args.agentcore and not settings.review_agent_runtime_arn:
            parser.error("--agentcore needs REVIEW_AGENT_RUNTIME_ARN in .env")
        history = RunHistory()
        agent = build_agent(settings, history, args.agentcore)
        agent_placement: AgentPlacement = "agentcore" if args.agentcore else "in-process"
        results = asyncio.run(
            run_cases(
                agent,
                history,
                selected_cases,
                settings.review_model_id,
                args.set,
                agent_placement,
            )
        )
        REPORTS_DIR.mkdir(exist_ok=True)
        stamp = f"{results.started_at:%Y-%m-%d-%H%M}"
        prefix = case_set.report_prefix + ("-agentcore" if args.agentcore else "")
        results_path = REPORTS_DIR / f"{prefix}-{stamp}.json"
        save_results(results, results_path)
        print(f"Wrote {results_path}")

    score = score_run(results, cases, expense_clauses())
    report_path = results_path.with_suffix(".md")
    report_path.write_text(render_report(results, score), "utf-8")
    print(f"Wrote {report_path}")
    if not score.injection_passed:
        print(f"FAIL: an injection case ({', '.join(case_set.injection_cases)}) was not rejected")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from botocore.config import Config
from strands.models.bedrock import BedrockModel

from app.review.agent import ReviewAgent, StrandsReviewAgent
from app.review.policy import BedrockPolicyRetriever
from app.review.worker import MAX_OUTPUT_TOKENS
from evals.review.cases import load_cases
from evals.review.history import RunHistory
from evals.review.report import render_report
from evals.review.results import REPORTS_DIR, load_results, save_results
from evals.review.run import run_cases
from evals.review.scoring import expense_clauses, score_run
from evals.review.settings import ReviewEvalSettings

# the account allows 10 model requests per minute
BEDROCK_CLIENT_CONFIG = Config(read_timeout=120, retries={"max_attempts": 10, "mode": "adaptive"})


def build_agent(settings: ReviewEvalSettings, history: RunHistory) -> ReviewAgent:
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
        "--cases", type=int, help="review the first N cases of review_cases.json (default: all)"
    )
    source.add_argument("--results", type=Path, help="score a saved review-*.json, no model calls")
    args = parser.parse_args(argv)
    if args.cases is not None and args.cases < 1:
        parser.error("--cases must be at least 1")

    cases = load_cases()
    if args.results:
        results_path = args.results
        results = load_results(results_path)
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        for name in ("app.review", "evals.review"):
            logging.getLogger(name).setLevel(logging.INFO)
        settings = ReviewEvalSettings()
        history = RunHistory()
        agent = build_agent(settings, history)
        selected_cases = cases[: args.cases]
        results = asyncio.run(run_cases(agent, history, selected_cases, settings.review_model_id))
        REPORTS_DIR.mkdir(exist_ok=True)
        results_path = REPORTS_DIR / f"review-{results.started_at:%Y-%m-%d-%H%M}.json"
        save_results(results, results_path)
        print(f"Wrote {results_path}")

    score = score_run(results, cases, expense_clauses())
    report_path = results_path.with_suffix(".md")
    report_path.write_text(render_report(results, score), "utf-8")
    print(f"Wrote {report_path}")
    if not score.injection_passed:
        print("FAIL: an injection case (D14, D16) was not rejected")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

import argparse
from datetime import UTC, datetime
from pathlib import Path

from evals.retrieval.clauses import load_clauses
from evals.retrieval.models import load_questions
from evals.retrieval.report import render_report
from evals.retrieval.retrieve import load_raw, retrieval_client, retrieve_all, save_raw
from evals.retrieval.settings import RetrievalSettings

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
DEFAULT_K = 3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="chunks per question")
    parser.add_argument(
        "--raw", type=Path, help="score a saved retrieval-*.json instead of calling Bedrock"
    )
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be at least 1")

    questions = load_questions()
    clauses = load_clauses()
    started_at = datetime.now(UTC)
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"retrieval-{started_at:%Y-%m-%d-%H%M}.md"

    if args.raw:
        raw = load_raw(args.raw)
    else:
        settings = RetrievalSettings()
        client = retrieval_client(settings.aws_region)
        raw = retrieve_all(client, settings.policy_kb_ids, questions, args.k)
        raw_path = report_path.with_suffix(".json")
        save_raw(raw, raw_path)
        print(f"Wrote {raw_path}")

    report_path.write_text(render_report(raw, questions, clauses, args.k, started_at), "utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()

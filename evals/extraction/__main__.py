import argparse
import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.extraction.extractor import BedrockExtractor
from app.extraction.settings import WorkerSettings
from evals.extraction.documents import available_ids, load_document
from evals.extraction.estimate import estimate_usage
from evals.extraction.metering import metered_client
from evals.extraction.pricing import model_price
from evals.extraction.report import RunInfo, format_usd, render_markdown, summarize
from evals.extraction.run import run_documents

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
DEFAULT_CONCURRENCY = 1


def main() -> None:
    known = available_ids()
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", help="document ids (default: all)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--yes", action="store_true", help="run without asking")
    args = parser.parse_args()
    unknown = sorted(set(args.ids) - set(known))
    if unknown:
        parser.error(f"unknown document ids: {' '.join(unknown)}")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    logging.basicConfig(level=logging.WARNING)

    settings = WorkerSettings()
    try:
        price = model_price(settings.bedrock_model_id)
    except KeyError as exc:
        parser.error(str(exc.args[0]))
    max_pages = settings.extraction_max_pages
    documents = [load_document(doc_id, max_pages) for doc_id in args.ids or known]
    estimated_cost = sum(
        (estimate_usage(document).cost(price) for document in documents), Decimal(0)
    )
    print(
        f"{len(documents)} documents, model {settings.bedrock_model_id}, "
        f"concurrency {args.concurrency}\n"
        f"Estimated cost: {format_usd(estimated_cost)} (one attempt each; retries cost more)"
    )
    if not args.yes and input("Run against Bedrock? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return

    started_at = datetime.now(UTC)
    results = asyncio.run(
        run_documents(
            documents, BedrockExtractor(settings, metered_client(settings)), args.concurrency
        )
    )
    labels = {d.doc_id: d.label for d in documents if d.label is not None}
    summary = summarize(results, price)
    info = RunInfo(started_at, settings.bedrock_model_id, args.concurrency, estimated_cost)

    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"extraction-{started_at:%Y-%m-%d-%H%M}.md"
    markdown = render_markdown(results, labels, summary, info, price)
    report_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()

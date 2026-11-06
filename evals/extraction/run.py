import asyncio
import logging
import time
from collections.abc import Sequence

from app.extraction.extractor import (
    ExpenseExtractor,
    InvalidExtraction,
    UnreadableDocument,
    ValidExtraction,
)
from app.extraction.schemas import ExtractedExpense
from evals.extraction.metering import DOCUMENT_USAGE
from evals.extraction.models import DocumentResult, EvalDocument, Outcome, TokenUsage
from evals.extraction.scoring import SCORED_FIELDS, score_fields

logger = logging.getLogger(__name__)


async def run_document(document: EvalDocument, extractor: ExpenseExtractor) -> DocumentResult:
    usage = TokenUsage()
    DOCUMENT_USAGE.set(usage)

    def result(
        outcome: Outcome,
        detail: str | None = None,
        expense: ExtractedExpense | None = None,
        latency_s: float | None = None,
    ) -> DocumentResult:
        fields: dict[str, bool] | None = None
        if document.label is not None:
            fields = (
                score_fields(document.label, expense)
                if expense is not None
                else dict.fromkeys(SCORED_FIELDS, False)
            )
        return DocumentResult(document.doc_id, outcome, detail, expense, fields, latency_s, usage)

    if document.unusable_reason is not None:
        return result("unusable_file", document.unusable_reason)

    started = time.perf_counter()
    try:
        extracted = await extractor.extract_expense(document.pages)
    except Exception as exc:
        logger.exception("extraction of %s raised", document.doc_id)
        return result("error", type(exc).__name__, latency_s=time.perf_counter() - started)
    latency_s = time.perf_counter() - started

    match extracted:
        case ValidExtraction(expense=expense):
            return result("extracted", expense=expense, latency_s=latency_s)
        case UnreadableDocument(reason=reason):
            return result("unreadable", reason, latency_s=latency_s)
        case InvalidExtraction(errors=errors):
            return result("invalid", errors, latency_s=latency_s)


async def run_documents(
    documents: Sequence[EvalDocument], extractor: ExpenseExtractor, concurrency: int
) -> list[DocumentResult]:
    limit = asyncio.Semaphore(concurrency)

    async def limited(document: EvalDocument) -> DocumentResult:
        async with limit:
            return await run_document(document, extractor)

    return list(await asyncio.gather(*(limited(document) for document in documents)))

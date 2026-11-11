import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.claims.models import Claim, Document
from app.claims.service import (
    ConcurrentTransitionError,
    InvalidTransitionError,
    transition,
    verify_upload,
)
from app.claims.status import ClaimStatus
from app.claims.storage import ObjectStorage
from app.core.hashing import file_sha256
from app.extraction.extractor import (
    ExpenseExtractor,
    InvalidExtraction,
    UnreadableDocument,
    ValidExtraction,
)
from app.extraction.models import Extraction, ExtractionLineItem
from app.extraction.pages import UnusableFileError, document_to_images
from app.extraction.queue import UploadedObject
from app.extraction.schemas import expense_warnings

logger = logging.getLogger(__name__)

RESUBMIT_ADVICE = "Please submit a new claim with a clear, complete photo or file."
UNREADABLE_REASON = "The document could not be read: {reason}. " + RESUBMIT_ADVICE
INVALID_EXTRACTION_REASON = (
    "The details on the document could not be extracted reliably. " + RESUBMIT_ADVICE
)
TECHNICAL_FAILURE_REASON = (
    "Extraction could not be completed because of a technical problem. Please submit a new claim."
)


async def process_upload(
    session: AsyncSession,
    storage: ObjectStorage,
    extractor: ExpenseExtractor,
    uploaded: UploadedObject,
    *,
    today: date,
    receive_count: int,
    max_receives: int,
    max_pages: int,
) -> uuid.UUID | None:
    started = await _start_extraction(session, storage, uploaded, redelivered=receive_count > 1)
    if not isinstance(started, Document):
        return started
    document = started
    claim_id = document.claim_id
    try:
        data = await storage.read(document.s3_key, document.version_id)
        document.sha256 = await file_sha256(data)
        result = await _extract_expense(extractor, document, data, max_pages)
        if isinstance(result, ValidExtraction):
            await _store_extraction(session, document, result, today)
            return claim_id
        await _fail_claim(session, claim_id, result)
    except Exception:
        await session.rollback()
        if receive_count < max_receives:
            raise
        logger.exception("extraction of claim %s failed on the last delivery", claim_id)
        await _fail_claim(session, claim_id, TECHNICAL_FAILURE_REASON)
    return None


async def _start_extraction(
    session: AsyncSession, storage: ObjectStorage, uploaded: UploadedObject, *, redelivered: bool
) -> Document | uuid.UUID | None:
    claim = await session.scalar(
        select(Claim)
        .join(Claim.document)
        .where(Document.s3_key == uploaded.key)
        .options(selectinload(Claim.document))
        .with_for_update(of=Claim)
        .execution_options(populate_existing=True)
    )
    if claim is None or claim.document is None:
        logger.warning("no claim has the uploaded object %s", uploaded.key)
        return None

    status = claim.status
    if status is ClaimStatus.PENDING_UPLOAD:
        claim.document.version_id = uploaded.version_id
        if not await verify_upload(session, storage, claim.document):
            await session.commit()
            return None
        status = ClaimStatus.UPLOADED
    if status is ClaimStatus.UPLOADED:
        await transition(session, claim.id, ClaimStatus.EXTRACTING)
    # a redelivery continues the extraction an earlier attempt of the same message started
    elif not (status is ClaimStatus.EXTRACTING and redelivered):
        if uploaded.version_id != claim.document.version_id:
            logger.warning(
                "claim %s: ignoring a later upload to its key (version %s); it keeps version %s",
                claim.id,
                uploaded.version_id,
                claim.document.version_id,
            )
        elif status is ClaimStatus.EXTRACTED and redelivered:
            await session.commit()
            return claim.id
        else:
            logger.info("claim %s is %s; nothing to extract", claim.id, status)
        await session.commit()
        return None
    await session.commit()
    return claim.document


async def _extract_expense(
    extractor: ExpenseExtractor, document: Document, data: bytes, max_pages: int
) -> ValidExtraction | str:
    try:
        pages = await asyncio.to_thread(document_to_images, data, document.content_type, max_pages)
    except UnusableFileError as exc:
        return f"{exc.reason}. {RESUBMIT_ADVICE}"

    outcome = await extractor.extract_expense(pages)
    match outcome:
        case ValidExtraction():
            return outcome
        case UnreadableDocument(reason=reason):
            return UNREADABLE_REASON.format(reason=reason)
        case InvalidExtraction(errors=errors):
            logger.warning("no valid extraction for claim %s: %s", document.claim_id, errors)
            return INVALID_EXTRACTION_REASON


async def _store_extraction(
    session: AsyncSession, document: Document, result: ValidExtraction, today: date
) -> None:
    existing = await session.scalar(
        select(Extraction.id).where(Extraction.document_id == document.id)
    )
    if existing is None:
        expense = result.expense
        session.add(
            Extraction(
                document_id=document.id,
                **expense.model_dump(exclude={"line_items"}),
                warnings=[warning.model_dump() for warning in expense_warnings(expense, today)],
                ai_model=result.model,
                line_items=[
                    ExtractionLineItem(position=position, **item.model_dump())
                    for position, item in enumerate(expense.line_items)
                ],
            )
        )
        await session.flush()
    await _finish_claim(session, document.claim_id, ClaimStatus.EXTRACTED)


async def _fail_claim(session: AsyncSession, claim_id: uuid.UUID, reason: str) -> None:
    await _finish_claim(session, claim_id, ClaimStatus.FAILED, reason)


async def _finish_claim(
    session: AsyncSession,
    claim_id: uuid.UUID,
    target: ClaimStatus,
    failure_reason: str | None = None,
) -> None:
    try:
        await transition(session, claim_id, target, failure_reason=failure_reason)
    except (ConcurrentTransitionError, InvalidTransitionError):
        # another delivery finished this claim first
        logger.info("claim %s already left extracting", claim_id)
        await session.rollback()
        return
    await session.commit()

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.claims.models import Claim, Document
from app.claims.service import transition
from app.claims.status import ClaimStatus
from app.core.config import WorkerSettings
from app.extraction.extractor import (
    ExtractionOutcome,
    InvalidExtraction,
    UnreadableDocument,
    ValidExtraction,
)
from app.extraction.models import Extraction
from app.extraction.queue import UploadMessage
from app.extraction.service import (
    INVALID_EXTRACTION_REASON,
    RESUBMIT_ADVICE,
    TECHNICAL_FAILURE_REASON,
)
from app.extraction.worker import ExtractionWorker
from tests.claims.fakes import EXE, FakeStorage
from tests.extraction.fakes import FakeExtractor, FakeQueue, document_bytes, expense

pytestmark = pytest.mark.integration

MODEL = "eu.anthropic.test-model"


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def worker_settings() -> WorkerSettings:
    return WorkerSettings()


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


def make_worker(
    db_session: AsyncSession,
    settings: WorkerSettings,
    queue: FakeQueue,
    storage: FakeStorage,
    *outcomes: ExtractionOutcome | Exception,
) -> tuple[ExtractionWorker, FakeExtractor]:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db_session  # the test's session, rolled back after the test

    extractor = FakeExtractor(*outcomes)
    return ExtractionWorker(settings, queue, sessions, storage, extractor), extractor


async def uploaded_file(
    db_session: AsyncSession,
    storage: FakeStorage,
    content: bytes,
    content_type: str = "application/pdf",
) -> Document:
    """A `pending_upload` claim whose file the browser has just put in S3"""
    claim = Claim(employee_sub="user-1", purpose="Lunch during client workshop trip to Hamburg")
    db_session.add(claim)
    await db_session.flush()
    document = Document(
        claim_id=claim.id,
        s3_key=f"claims/{claim.id}/{uuid.uuid4()}",
        original_filename="receipt",
        content_type=content_type,
    )
    db_session.add(document)
    await db_session.commit()
    storage.objects[document.s3_key] = content
    return document


def event(document: Document, receive_count: int = 1) -> UploadMessage:
    return UploadMessage(f"handle-{receive_count}", [document.s3_key], receive_count)


async def claim_of(db_session: AsyncSession, document: Document) -> Claim:
    claim = await db_session.scalar(
        select(Claim)
        .where(Claim.id == document.claim_id)
        .options(selectinload(Claim.document))
        .execution_options(populate_existing=True)
    )
    assert claim is not None
    return claim


async def extractions(db_session: AsyncSession, document: Document) -> list[Extraction]:
    rows = await db_session.scalars(
        select(Extraction)
        .where(Extraction.document_id == document.id)
        .options(selectinload(Extraction.line_items))
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def test_upload_event_extracts_the_claim(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    expected = expense("D01")
    worker, extractor = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(expected, MODEL)
    )

    await worker.handle_message(event(document))

    claim = await claim_of(db_session, document)
    assert claim.status is ClaimStatus.EXTRACTED
    assert claim.document is not None
    assert claim.document.size_bytes == len(document_bytes("D01.pdf"))
    (row,) = await extractions(db_session, document)
    assert row.vendor_name == expected.vendor_name
    assert row.document_date == expected.document_date
    assert row.document_time == expected.document_time
    assert row.total == expected.total
    assert row.category == expected.category
    assert row.ai_model == MODEL
    assert row.warnings == []
    assert [(item.position, item.description, item.amount) for item in row.line_items] == [
        (position, item.description, item.amount)
        for position, item in enumerate(expected.line_items)
    ]
    assert len(extractor.calls[0]) == 1  # one page image
    assert queue.deleted == ["handle-1"]


async def test_worker_run_handles_received_messages_until_stopped(
    db_session: AsyncSession,
    storage: FakeStorage,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    queue = FakeQueue(event(document))
    worker, _ = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(expense("D01"), MODEL)
    )
    stop = asyncio.Event()
    receive = queue.receive_messages

    async def receive_once() -> list[UploadMessage]:
        stop.set()
        return await receive()

    queue.receive_messages = receive_once  # type: ignore[method-assign]

    await worker.run(stop)

    assert (await claim_of(db_session, document)).status is ClaimStatus.EXTRACTED
    assert queue.deleted == ["handle-1"]


async def test_unreadable_photo_fails_with_a_reason_for_the_employee(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("E10.jpg"), "image/jpeg")
    worker, _ = make_worker(
        db_session, worker_settings, queue, storage, UnreadableDocument("the total is cut off")
    )

    await worker.handle_message(event(document))

    claim = await claim_of(db_session, document)
    assert claim.status is ClaimStatus.FAILED
    assert claim.failure_reason == (
        "The document could not be read: the total is cut off. Please submit a new claim with a "
        "clear, complete photo or file."
    )
    assert await extractions(db_session, document) == []
    assert queue.deleted == ["handle-1"]


async def test_invalid_extraction_is_never_stored(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    worker, _ = make_worker(
        db_session, worker_settings, queue, storage, InvalidExtraction("total: Input should be > 0")
    )

    await worker.handle_message(event(document))

    claim = await claim_of(db_session, document)
    assert claim.status is ClaimStatus.FAILED
    assert claim.failure_reason == INVALID_EXTRACTION_REASON
    assert await extractions(db_session, document) == []


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"%PDF-1.7 but nothing else", "The PDF could not be opened"),
        (document_bytes("E01.pdf"), "The PDF has 2 pages; at most 1 can be processed"),
    ],
    ids=["broken-pdf", "too-many-pages"],
)
async def test_file_that_cannot_become_pages_fails_without_a_model_call(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
    content: bytes,
    reason: str,
) -> None:
    document = await uploaded_file(db_session, storage, content)
    settings = worker_settings.model_copy(update={"extraction_max_pages": 1})
    worker, extractor = make_worker(
        db_session, settings, queue, storage, ValidExtraction(expense("D01"), MODEL)
    )

    await worker.handle_message(event(document))

    claim = await claim_of(db_session, document)
    assert claim.status is ClaimStatus.FAILED
    assert claim.failure_reason == f"{reason}. {RESUBMIT_ADVICE}"
    assert extractor.calls == []


async def test_error_is_retried_by_the_queue_and_the_redelivery_finishes(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    """A crash in `extracting` leaves the message in the queue; its redelivery stores one row."""
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    worker, extractor = make_worker(
        db_session,
        worker_settings,
        queue,
        storage,
        RuntimeError("Bedrock throttled"),
        ValidExtraction(expense("D01"), MODEL),
    )

    await worker.handle_message(event(document, receive_count=1))

    assert (await claim_of(db_session, document)).status is ClaimStatus.EXTRACTING
    assert queue.deleted == []

    await worker.handle_message(event(document, receive_count=2))

    assert (await claim_of(db_session, document)).status is ClaimStatus.EXTRACTED
    assert len(await extractions(db_session, document)) == 1
    assert len(extractor.calls) == 2
    assert queue.deleted == ["handle-2"]


async def test_error_on_the_last_delivery_fails_the_claim(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    worker, _ = make_worker(
        db_session, worker_settings, queue, storage, RuntimeError("Bedrock is down")
    )
    last = worker_settings.extraction_max_receives
    async with db_session.begin_nested():
        await transition(db_session, document.claim_id, ClaimStatus.UPLOADED)
        await transition(db_session, document.claim_id, ClaimStatus.EXTRACTING)
    await db_session.commit()

    await worker.handle_message(event(document, receive_count=last))

    claim = await claim_of(db_session, document)
    assert claim.status is ClaimStatus.FAILED
    assert claim.failure_reason == TECHNICAL_FAILURE_REASON
    assert queue.deleted == [f"handle-{last}"]


async def test_checks_are_stored_as_warnings_and_values_stay_as_extracted(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    next_month = datetime.now(UTC).date() + timedelta(days=30)
    odd = expense("D01", total="25.00", document_date=next_month.isoformat())
    worker, _ = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(odd, MODEL)
    )

    await worker.handle_message(event(document))

    (row,) = await extractions(db_session, document)
    assert [warning["code"] for warning in row.warnings] == ["sum_mismatch", "future_date"]
    assert row.total == Decimal("25.00")
    assert row.document_date == next_month


async def test_the_same_upload_twice_gives_one_extraction(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    worker, extractor = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(expense("D01"), MODEL)
    )

    await worker.handle_message(UploadMessage("first", [document.s3_key], 1))
    await worker.handle_message(UploadMessage("duplicate", [document.s3_key], 1))

    count = await db_session.scalar(
        select(func.count()).select_from(Extraction).where(Extraction.document_id == document.id)
    )
    assert count == 1
    assert len(extractor.calls) == 1
    assert queue.deleted == ["first", "duplicate"]


async def test_a_second_event_leaves_a_claim_another_worker_is_extracting(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    document = await uploaded_file(db_session, storage, document_bytes("D01.pdf"))
    async with db_session.begin_nested():
        await transition(db_session, document.claim_id, ClaimStatus.UPLOADED)
        await transition(db_session, document.claim_id, ClaimStatus.EXTRACTING)
    await db_session.commit()
    worker, extractor = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(expense("D01"), MODEL)
    )

    await worker.handle_message(event(document, receive_count=1))

    assert (await claim_of(db_session, document)).status is ClaimStatus.EXTRACTING
    assert extractor.calls == []
    assert queue.deleted == ["handle-1"]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (EXE, "The file is not a valid PDF"),
        (b"%PDF-" + b"0" * (10 * 1024 * 1024), "The file is larger than 10 MB"),
        (None, "The uploaded file could not be found"),
    ],
    ids=["executable-as-pdf", "oversized", "missing"],
)
async def test_rejected_file_is_deleted_and_fails_the_claim(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
    content: bytes | None,
    reason: str,
) -> None:
    """The T04 file checks, now run on the S3 event instead of `upload-complete`"""
    document = await uploaded_file(db_session, storage, content or b"")
    if content is None:
        del storage.objects[document.s3_key]
    worker, extractor = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(expense("D01"), MODEL)
    )

    await worker.handle_message(event(document))

    claim = await claim_of(db_session, document)
    assert claim.status is ClaimStatus.FAILED
    assert claim.failure_reason == reason
    assert storage.deleted == [document.s3_key]
    assert extractor.calls == []
    assert queue.deleted == ["handle-1"]


async def test_event_for_an_unknown_object_is_dropped(
    db_session: AsyncSession,
    storage: FakeStorage,
    queue: FakeQueue,
    worker_settings: WorkerSettings,
) -> None:
    worker, extractor = make_worker(
        db_session, worker_settings, queue, storage, ValidExtraction(expense("D01"), MODEL)
    )

    await worker.handle_message(UploadMessage("handle-1", [f"claims/{uuid.uuid4()}/x"], 1))
    await worker.handle_message(UploadMessage("test-event", [], 1))

    assert extractor.calls == []
    assert queue.deleted == ["handle-1", "test-event"]

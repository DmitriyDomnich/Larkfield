import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.models import Claim
from app.claims.service import transition
from app.claims.status import ClaimStatus as S
from app.core.metrics import BedrockRunError, TokenUsage
from app.review.agent import NoValidProposal, ReviewOutcome, ValidProposal
from app.review.claim_data import ClaimUnderReview
from app.review.models import ClaimAnswer, Decision, Proposal, ReviewerDecision
from app.review.proposal import ReviewProposal
from app.review.queue import ReviewMessage
from app.review.service import NO_VALID_PROPOSAL_REASON, TECHNICAL_FAILURE_REASON
from app.review.settings import ReviewWorkerSettings
from app.review.worker import ReviewWorker
from tests.core.fakes import RecordingMetrics
from tests.notifications.fakes import FakeNotificationService
from tests.review.db import extracted_claim
from tests.review.fakes import FakeAgent, FakeReviewQueue, proposal_input

pytestmark = pytest.mark.integration

MODEL = "eu.anthropic.test-review-model"
NO_TOKENS = TokenUsage()


@pytest.fixture
def review_settings() -> ReviewWorkerSettings:
    return ReviewWorkerSettings()


def make_worker(
    db_session: AsyncSession,
    settings: ReviewWorkerSettings,
    queue: FakeReviewQueue,
    *outcomes: ReviewOutcome | Exception,
    notification_service: FakeNotificationService | None = None,
    metrics: RecordingMetrics | None = None,
) -> tuple[ReviewWorker, FakeAgent]:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db_session  # the test's session, rolled back after the test

    agent = FakeAgent(*outcomes)
    notification_service = notification_service or FakeNotificationService()
    worker = ReviewWorker(
        settings, queue, sessions, agent, notification_service, metrics or RecordingMetrics()
    )
    return worker, agent


def valid(
    decision: str = "approve",
    reasons: Sequence[tuple[str, str]] = (("2.1", "lunch EUR 25, dinner EUR 45"),),
    duplicate_of: uuid.UUID | None = None,
    usage: TokenUsage = NO_TOKENS,
) -> ValidProposal:
    proposal = ReviewProposal.model_validate(
        proposal_input(decision, reasons, duplicate_of=duplicate_of)
    )
    return ValidProposal(proposal, ["FAQ-13", "2.1"], MODEL, usage)


def request(claim_id: uuid.UUID | None, receive_count: int = 1) -> ReviewMessage:
    return ReviewMessage(f"handle-{receive_count}", claim_id, receive_count)


async def claim_row(db_session: AsyncSession, claim_id: uuid.UUID) -> Claim:
    claim = await db_session.scalar(
        select(Claim).where(Claim.id == claim_id).execution_options(populate_existing=True)
    )
    assert claim is not None
    return claim


async def proposals(db_session: AsyncSession, claim_id: uuid.UUID) -> list[Proposal]:
    return list(await db_session.scalars(select(Proposal).where(Proposal.claim_id == claim_id)))


async def test_an_extracted_claim_gets_a_stored_proposal_and_goes_in_review(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    worker, agent = make_worker(db_session, review_settings, queue, valid())

    await worker.handle_message(request(claim_id))

    assert (await claim_row(db_session, claim_id)).status is S.IN_REVIEW
    [proposal] = await proposals(db_session, claim_id)
    assert proposal.decision is Decision.APPROVE
    assert proposal.reasons == [
        {
            "clause_id": "2.1",
            "quote": "lunch EUR 25, dinner EUR 45",
            "explanation": "Applies to this claim.",
        }
    ]
    assert proposal.missing_information == []
    assert proposal.duplicate_of is None
    assert proposal.ai_model == MODEL
    assert proposal.retrieved_clauses == ["FAQ-13", "2.1"]
    assert queue.deleted == ["handle-1"]
    # the agent got the claim and its extraction
    [reviewed] = agent.reviewed
    assert reviewed.claim_id == claim_id
    assert reviewed.purpose.startswith("Lunch during client workshop trip")
    assert str(reviewed.expense.total) == "18.50"


async def test_needs_info_and_duplicate_proposals_are_stored_as_given(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    earlier = await extracted_claim(db_session, "D01", status=S.IN_REVIEW)
    claim_id = await extracted_claim(db_session, "D17")
    duplicate = valid(
        decision="reject", reasons=[("1.4", "the later claim is rejected")], duplicate_of=earlier
    )
    worker, _ = make_worker(db_session, review_settings, FakeReviewQueue(), duplicate)

    await worker.handle_message(request(claim_id))

    [proposal] = await proposals(db_session, claim_id)
    assert proposal.decision is Decision.REJECT
    assert proposal.duplicate_of == earlier


async def test_no_valid_proposal_fails_the_claim_with_a_reason(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    worker, _ = make_worker(db_session, review_settings, queue, NoValidProposal("limit_turns"))

    await worker.handle_message(request(claim_id))

    claim = await claim_row(db_session, claim_id)
    assert claim.status is S.FAILED
    assert claim.failure_reason == NO_VALID_PROPOSAL_REASON
    assert await proposals(db_session, claim_id) == []
    assert queue.deleted == ["handle-1"]


async def test_an_error_is_retried_by_the_queue_and_the_redelivery_finishes(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    worker, _ = make_worker(
        db_session, review_settings, queue, RuntimeError("Bedrock throttled"), valid()
    )

    await worker.handle_message(request(claim_id, receive_count=1))

    assert (await claim_row(db_session, claim_id)).status is S.EXTRACTED
    assert queue.deleted == []

    await worker.handle_message(request(claim_id, receive_count=2))

    assert (await claim_row(db_session, claim_id)).status is S.IN_REVIEW
    assert queue.deleted == ["handle-2"]


async def test_an_error_on_the_last_delivery_fails_the_claim(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    worker, _ = make_worker(db_session, review_settings, queue, RuntimeError("Bedrock down"))

    last = review_settings.review_max_receives
    await worker.handle_message(request(claim_id, receive_count=last))

    claim = await claim_row(db_session, claim_id)
    assert claim.status is S.FAILED
    assert claim.failure_reason == TECHNICAL_FAILURE_REASON
    assert queue.deleted == [f"handle-{last}"]


@pytest.mark.parametrize("status", [S.IN_REVIEW, S.APPROVED, S.FAILED])
async def test_a_claim_that_is_not_extracted_is_not_reviewed(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings, status: S
) -> None:
    claim_id = await extracted_claim(db_session, "D01", status=status)
    queue = FakeReviewQueue()
    worker, agent = make_worker(db_session, review_settings, queue, valid())

    await worker.handle_message(request(claim_id))

    assert agent.reviewed == []
    assert (await claim_row(db_session, claim_id)).status is status
    assert queue.deleted == ["handle-1"]


async def test_a_request_for_an_unknown_claim_or_a_bad_message_is_dropped(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    queue = FakeReviewQueue()
    worker, agent = make_worker(db_session, review_settings, queue, valid())

    await worker.handle_message(request(uuid.uuid4(), receive_count=1))
    await worker.handle_message(ReviewMessage("handle-bad", None, 1))

    assert agent.reviewed == []
    assert queue.deleted == ["handle-1", "handle-bad"]


async def test_a_second_delivery_that_finishes_later_stores_nothing(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    """Two deliveries of the same request reviewed at once: one proposal, one in_review"""
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    slow_started, fast_done = asyncio.Event(), asyncio.Event()

    class SlowAgent(FakeAgent):
        async def review(self, claim: ClaimUnderReview) -> ReviewOutcome:
            slow_started.set()
            await fast_done.wait()
            return await super().review(claim)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db_session

    slow = ReviewWorker(
        review_settings,
        queue,
        sessions,
        SlowAgent(valid()),
        FakeNotificationService(),
        RecordingMetrics(),
    )
    fast, _ = make_worker(db_session, review_settings, queue, valid(decision="reject"))

    # the slow delivery loads the claim while it is still extracted, then waits in the agent
    slow_task = asyncio.create_task(slow.handle_message(request(claim_id, receive_count=1)))
    await slow_started.wait()
    await fast.handle_message(request(claim_id, receive_count=2))
    fast_done.set()
    await slow_task

    [proposal] = await proposals(db_session, claim_id)
    assert proposal.decision is Decision.REJECT
    assert (await claim_row(db_session, claim_id)).status is S.IN_REVIEW
    assert sorted(queue.deleted) == ["handle-1", "handle-2"]


async def test_worker_run_handles_received_requests_until_stopped(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue(request(claim_id))
    worker, _ = make_worker(db_session, review_settings, queue, valid())
    stop = asyncio.Event()
    receive = queue.receive_messages

    async def receive_once() -> list[ReviewMessage]:
        stop.set()
        return await receive()

    queue.receive_messages = receive_once  # type: ignore[method-assign]

    await worker.run(stop)

    assert (await claim_row(db_session, claim_id)).status is S.IN_REVIEW
    assert queue.deleted == ["handle-1"]


async def test_the_outcome_of_each_review_is_logged(
    db_session: AsyncSession,
    review_settings: ReviewWorkerSettings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stored = await extracted_claim(db_session, "D01")
    failed = await extracted_claim(db_session, "D02")
    queue = FakeReviewQueue()
    worker, _ = make_worker(
        db_session, review_settings, queue, valid(), NoValidProposal("limit_turns")
    )

    with caplog.at_level(logging.INFO, logger="app.review.service"):
        await worker.handle_message(request(stored))
        await worker.handle_message(request(failed))

    assert f"claim {stored}: proposal approve stored, citing ['2.1']; claim is in_review" in (
        caplog.messages
    )
    assert f"claim {failed}: failed: {NO_VALID_PROPOSAL_REASON}" in caplog.messages


async def test_a_claim_the_review_fails_emails_the_employee(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    notification_service = FakeNotificationService()
    worker, _ = make_worker(
        db_session,
        review_settings,
        FakeReviewQueue(),
        NoValidProposal("limit_turns"),
        notification_service=notification_service,
    )

    await worker.handle_message(request(claim_id))

    [sent] = notification_service.sent
    assert sent.claim_id == claim_id
    assert sent.status is S.FAILED
    assert sent.failure_reason == NO_VALID_PROPOSAL_REASON


async def test_a_claim_going_in_review_sends_no_email(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    notification_service = FakeNotificationService()
    worker, _ = make_worker(
        db_session,
        review_settings,
        FakeReviewQueue(),
        valid(),
        notification_service=notification_service,
    )

    await worker.handle_message(request(claim_id))

    assert notification_service.sent == []


async def test_a_failed_email_send_still_deletes_the_request(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    worker, _ = make_worker(
        db_session,
        review_settings,
        queue,
        NoValidProposal("limit_turns"),
        notification_service=FakeNotificationService(error=RuntimeError("SQS down")),
    )

    await worker.handle_message(request(claim_id))

    assert (await claim_row(db_session, claim_id)).status is S.FAILED
    assert queue.deleted == ["handle-1"]


async def test_a_claim_going_in_review_records_its_tokens_and_no_failure(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    metrics = RecordingMetrics()
    worker, _ = make_worker(
        db_session,
        review_settings,
        FakeReviewQueue(),
        valid(usage=TokenUsage(12000, 900)),
        metrics=metrics,
    )

    await worker.handle_message(request(claim_id))

    assert metrics.values("BedrockInputTokens") == [("review", str(claim_id), 12000)]
    assert metrics.values("BedrockOutputTokens") == [("review", str(claim_id), 900)]
    assert metrics.values("ClaimsFailed") == []


async def test_no_valid_proposal_is_counted_as_failed_with_its_tokens(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    metrics = RecordingMetrics()
    worker, _ = make_worker(
        db_session,
        review_settings,
        FakeReviewQueue(),
        NoValidProposal("limit_turns", TokenUsage(30000, 2000)),
        metrics=metrics,
    )

    await worker.handle_message(request(claim_id))

    assert metrics.values("ClaimsFailed") == [("review", str(claim_id), 1)]
    assert metrics.values("BedrockInputTokens") == [("review", str(claim_id), 30000)]


async def test_an_error_is_counted_as_failed_only_on_the_last_delivery(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    metrics = RecordingMetrics()
    worker, _ = make_worker(
        db_session,
        review_settings,
        FakeReviewQueue(),
        RuntimeError("Bedrock down"),
        metrics=metrics,
    )
    last = review_settings.review_max_receives

    for receive_count in range(1, last):
        await worker.handle_message(request(claim_id, receive_count=receive_count))
        assert metrics.values("ClaimsFailed") == []
    await worker.handle_message(request(claim_id, receive_count=last))

    assert metrics.values("ClaimsFailed") == [("review", str(claim_id), 1)]
    assert metrics.values("BedrockInputTokens") == []


async def test_a_claim_that_is_not_extracted_counts_nothing(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01", status=S.FAILED)
    metrics = RecordingMetrics()
    worker, _ = make_worker(
        db_session, review_settings, FakeReviewQueue(), valid(), metrics=metrics
    )

    await worker.handle_message(request(claim_id))

    assert metrics.lines() == []


async def test_tokens_of_a_failed_bedrock_run_are_recorded_before_the_retry(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01")
    queue = FakeReviewQueue()
    metrics = RecordingMetrics()
    worker, _ = make_worker(
        db_session,
        review_settings,
        queue,
        BedrockRunError(TokenUsage(20000, 1500)),
        metrics=metrics,
    )

    await worker.handle_message(request(claim_id))

    assert metrics.values("BedrockInputTokens") == [("review", str(claim_id), 20000)]
    assert metrics.values("ClaimsFailed") == []
    assert queue.deleted == []


async def answered_round(
    db_session: AsyncSession,
    claim_id: uuid.UUID,
    corrected_fields: dict[str, object] | None,
    created_at: datetime,
) -> None:
    """A needs_info round the employee answered, with the reviewer's corrections"""
    proposal = Proposal(
        claim_id=claim_id,
        decision=Decision.NEEDS_INFO,
        reasons=[{"clause_id": "2.2", "quote": "q", "explanation": "e"}],
        missing_information=["Attendees"],
        ai_model=MODEL,
        created_at=created_at,
    )
    db_session.add(proposal)
    await db_session.flush()
    decision = ReviewerDecision(
        proposal_id=proposal.id,
        reviewer_sub="reviewer-1",
        decision=Decision.NEEDS_INFO,
        comment="Who attended?",
        corrected_fields=corrected_fields,
        created_at=created_at,
    )
    db_session.add(decision)
    await db_session.flush()
    db_session.add(ClaimAnswer(reviewer_decision_id=decision.id, message="Just me."))
    await db_session.flush()


async def test_the_second_round_reviews_the_newest_corrections_with_recomputed_warnings(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01", status=S.NEEDS_INFO)
    first, second = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC)
    await answered_round(db_session, claim_id, {"total": "50.00"}, first)
    await answered_round(db_session, claim_id, {"total": "99.99", "category": "other"}, second)
    await transition(db_session, claim_id, S.EXTRACTED)
    await db_session.commit()
    worker, agent = make_worker(db_session, review_settings, FakeReviewQueue(), valid())

    await worker.handle_message(request(claim_id))

    [reviewed] = agent.reviewed
    assert str(reviewed.expense.total) == "99.99"
    assert reviewed.expense.category == "other"
    assert reviewed.expense.vendor_name == "Brauhaus am Markt"
    assert [warning["code"] for warning in reviewed.warnings] == ["sum_mismatch"]
    assert "99.99" in reviewed.warnings[0]["message"]


async def test_a_round_without_corrections_reviews_the_extraction_as_stored(
    db_session: AsyncSession, review_settings: ReviewWorkerSettings
) -> None:
    claim_id = await extracted_claim(db_session, "D01", status=S.NEEDS_INFO)
    await answered_round(db_session, claim_id, None, datetime(2026, 11, 1, tzinfo=UTC))
    await transition(db_session, claim_id, S.EXTRACTED)
    await db_session.commit()
    worker, agent = make_worker(db_session, review_settings, FakeReviewQueue(), valid())

    await worker.handle_message(request(claim_id))

    [reviewed] = agent.reviewed
    assert str(reviewed.expense.total) == "18.50"
    assert reviewed.warnings == []

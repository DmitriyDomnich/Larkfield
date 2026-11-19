"""Reviewer decisions, needs_info answers and the review history against a real PostgreSQL.
SQS (notification_service, review requests) is faked."""

import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_token_verifier
from app.claims.models import Claim
from app.claims.service import transition
from app.claims.status import ClaimStatus as S
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.notifications.queue import get_notification_service
from app.review.agent import ValidProposal
from app.review.models import ClaimAnswer, Decision, Proposal, ReviewerDecision
from app.review.proposal import ReviewProposal
from app.review.queue import ReviewMessage, get_review_requests
from app.review.settings import ReviewWorkerSettings
from app.review.worker import ReviewWorker
from tests.claims.fakes import auth
from tests.notifications.fakes import FakeNotificationService
from tests.review.db import extracted_claim
from tests.review.fakes import FakeAgent, FakeReviewQueue, proposal_input
from tests.tokens import make_verifier

pytestmark = pytest.mark.integration

MODEL = "eu.anthropic.test-review-model"
EMPLOYEE = "employee-1"
REVIEWER = "reviewer-1"
ATTENDEES_MISSING = ["The names and companies of all attendees"]
ATTENDEES = [
    {"name": "D. Domnic", "company": "Larkfield"},
    {"name": "J. Weber", "company": "Meridian Health"},
]


@pytest.fixture
def notification_service() -> FakeNotificationService:
    return FakeNotificationService()


@pytest.fixture
def review_requests() -> FakeReviewQueue:
    return FakeReviewQueue()


@pytest.fixture
async def api(
    db_session: AsyncSession,
    settings: Settings,
    notification_service: FakeNotificationService,
    review_requests: FakeReviewQueue,
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_token_verifier] = lambda: make_verifier(settings)
    app.dependency_overrides[get_notification_service] = lambda: notification_service
    app.dependency_overrides[get_review_requests] = lambda: review_requests
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def as_(settings: Settings) -> Any:
    def headers(sub: str = EMPLOYEE, role: str = "employee") -> dict[str, str]:
        return auth(settings, sub=sub, role=role)

    return headers


@pytest.fixture
def reviewer(as_: Any) -> dict[str, str]:
    headers: dict[str, str] = as_(REVIEWER, "reviewer")
    return headers


async def create_claim_in_review(
    session: AsyncSession,
    case_id: str = "D04",
    *,
    employee_sub: str = EMPLOYEE,
    decision: str = "approve",
    missing_information: Sequence[str] = (),
) -> uuid.UUID:
    claim_id = await extracted_claim(session, case_id, employee_sub=employee_sub)
    await add_proposal(session, claim_id, decision, missing_information)
    await transition(session, claim_id, S.IN_REVIEW)
    await session.commit()
    return claim_id


async def add_proposal(
    session: AsyncSession,
    claim_id: uuid.UUID,
    decision: str,
    missing_information: Sequence[str] = (),
) -> None:
    session.add(
        Proposal(
            claim_id=claim_id,
            decision=Decision(decision),
            reasons=[{"clause_id": "2.2", "quote": "q", "explanation": "e"}],
            missing_information=list(missing_information),
            ai_model=MODEL,
            # every row of a test shares one transaction, so now() would tie the rounds
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def create_needs_info_claim(
    session: AsyncSession, api: AsyncClient, reviewer: dict[str, str], **claim: Any
) -> uuid.UUID:
    """A D04 claim (client dinner, no attendees) the reviewer sent back to the employee"""
    claim_id = await create_claim_in_review(
        session, decision="needs_info", missing_information=ATTENDEES_MISSING, **claim
    )
    response = await api.post(
        f"/claims/{claim_id}/decision",
        json={"decision": "needs_info", "comment": "Please list the attendees."},
        headers=reviewer,
    )
    assert response.status_code == 201, response.text
    return claim_id


async def load_claim(session: AsyncSession, claim_id: uuid.UUID) -> Claim:
    claim = await session.scalar(
        select(Claim).where(Claim.id == claim_id).execution_options(populate_existing=True)
    )
    assert claim is not None
    return claim


async def list_decisions(session: AsyncSession, claim_id: uuid.UUID) -> list[ReviewerDecision]:
    rows = await session.scalars(
        select(ReviewerDecision)
        .join(ReviewerDecision.proposal)
        .where(Proposal.claim_id == claim_id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def list_answers(session: AsyncSession, claim_id: uuid.UUID) -> list[ClaimAnswer]:
    rows = await session.scalars(
        select(ClaimAnswer)
        .join(ReviewerDecision, ClaimAnswer.reviewer_decision_id == ReviewerDecision.id)
        .join(ReviewerDecision.proposal)
        .where(Proposal.claim_id == claim_id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


# --- deciding ---------------------------------------------------------------------------------


async def test_a_reviewer_approves_as_proposed_without_a_comment(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    notification_service: FakeNotificationService,
) -> None:
    claim_id = await create_claim_in_review(db_session)

    response = await api.post(
        f"/claims/{claim_id}/decision", json={"decision": "approve"}, headers=reviewer
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] == "approve"
    assert body["reviewer_sub"] == REVIEWER
    assert body["comment"] is None
    assert (await load_claim(db_session, claim_id)).status is S.APPROVED
    [decision] = await list_decisions(db_session, claim_id)
    assert str(decision.id) == body["id"]
    [sent] = notification_service.sent
    assert (sent.claim_id, sent.status, sent.employee_sub) == (claim_id, S.APPROVED, EMPLOYEE)


@pytest.mark.parametrize(
    ("decision", "status"), [("reject", S.REJECTED), ("needs_info", S.NEEDS_INFO)]
)
async def test_a_decision_that_differs_from_the_proposal_needs_a_comment_and_emails_it(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    notification_service: FakeNotificationService,
    decision: str,
    status: S,
) -> None:
    claim_id = await create_claim_in_review(db_session, decision="approve")
    comment = "The attendee list is missing (2.2)."

    response = await api.post(
        f"/claims/{claim_id}/decision",
        json={"decision": decision, "comment": comment},
        headers=reviewer,
    )

    assert response.status_code == 201, response.text
    assert (await load_claim(db_session, claim_id)).status is status
    [sent] = notification_service.sent
    assert sent.status is status
    assert sent.comment == comment


@pytest.mark.parametrize(
    ("proposed", "decision", "comment"),
    [
        pytest.param("approve", "reject", None, id="differs"),
        pytest.param("needs_info", "needs_info", None, id="needs-info"),
        pytest.param("needs_info", "needs_info", "   ", id="needs-info-blank-comment"),
        pytest.param("reject", "approve", "", id="differs-empty-comment"),
        pytest.param("reject", "reject", None, id="reject-as-proposed"),
    ],
)
async def test_a_missing_comment_is_refused_and_nothing_changes(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    notification_service: FakeNotificationService,
    proposed: str,
    decision: str,
    comment: str | None,
) -> None:
    missing = ATTENDEES_MISSING if proposed == "needs_info" else ()
    claim_id = await create_claim_in_review(
        db_session, decision=proposed, missing_information=missing
    )

    response = await api.post(
        f"/claims/{claim_id}/decision",
        json={"decision": decision, "comment": comment},
        headers=reviewer,
    )

    assert response.status_code == 422
    assert "comment is required" in response.json()["detail"]
    assert (await load_claim(db_session, claim_id)).status is S.IN_REVIEW
    assert await list_decisions(db_session, claim_id) == []
    assert notification_service.sent == []


async def test_corrected_fields_are_stored_as_sent_and_the_extraction_is_kept(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str]
) -> None:
    claim_id = await create_claim_in_review(db_session)

    response = await api.post(
        f"/claims/{claim_id}/decision",
        json={
            "decision": "approve",
            "corrected_fields": {"total": "142.50", "tip_amount": None, "vendor_name": "Lumen"},
        },
        headers=reviewer,
    )

    assert response.status_code == 201, response.text
    expected = {"total": "142.50", "tip_amount": None, "vendor_name": "Lumen"}
    assert response.json()["corrected_fields"] == expected
    [decision] = await list_decisions(db_session, claim_id)
    assert decision.corrected_fields == expected


async def test_a_reviewer_cannot_decide_their_own_claim(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    notification_service: FakeNotificationService,
) -> None:
    claim_id = await create_claim_in_review(db_session, employee_sub=REVIEWER)

    response = await api.post(
        f"/claims/{claim_id}/decision", json={"decision": "approve"}, headers=reviewer
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "A reviewer cannot decide their own claim"
    assert (await load_claim(db_session, claim_id)).status is S.IN_REVIEW
    assert await list_decisions(db_session, claim_id) == []
    assert notification_service.sent == []


async def test_another_reviewer_can_decide_a_reviewers_claim(
    api: AsyncClient, db_session: AsyncSession, as_: Any
) -> None:
    claim_id = await create_claim_in_review(db_session, employee_sub=REVIEWER)

    response = await api.post(
        f"/claims/{claim_id}/decision",
        json={"decision": "approve"},
        headers=as_("reviewer-2", "reviewer"),
    )

    assert response.status_code == 201


@pytest.mark.parametrize("status", [S.EXTRACTED, S.APPROVED, S.NEEDS_INFO, S.FAILED])
async def test_only_a_claim_in_review_can_be_decided(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str], status: S
) -> None:
    claim_id = await extracted_claim(db_session, "D04", status=status)

    response = await api.post(
        f"/claims/{claim_id}/decision", json={"decision": "approve"}, headers=reviewer
    )

    assert response.status_code == 409
    assert (await load_claim(db_session, claim_id)).status is status


async def test_a_proposal_is_decided_once(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str], as_: Any
) -> None:
    claim_id = await create_claim_in_review(db_session)
    first = await api.post(
        f"/claims/{claim_id}/decision", json={"decision": "approve"}, headers=reviewer
    )

    second = await api.post(
        f"/claims/{claim_id}/decision",
        json={"decision": "reject", "comment": "Too late."},
        headers=as_("reviewer-2", "reviewer"),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "The claim cannot move from approved to rejected"
    assert len(await list_decisions(db_session, claim_id)) == 1


async def test_deciding_an_unknown_claim_is_404(api: AsyncClient, reviewer: dict[str, str]) -> None:
    response = await api.post(
        f"/claims/{uuid.uuid4()}/decision", json={"decision": "approve"}, headers=reviewer
    )

    assert response.status_code == 404


async def test_a_decision_succeeds_when_the_email_cannot_be_queued(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    notification_service: FakeNotificationService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    claim_id = await create_claim_in_review(db_session)
    notification_service.error = RuntimeError("SQS unavailable")

    with caplog.at_level(logging.ERROR, logger="app.notifications.queue"):
        response = await api.post(
            f"/claims/{claim_id}/decision", json={"decision": "approve"}, headers=reviewer
        )

    assert response.status_code == 201
    assert (await load_claim(db_session, claim_id)).status is S.APPROVED
    assert f"the approved notification for claim {claim_id} could not be queued" in (
        caplog.messages
    )


# --- answering needs_info ---------------------------------------------------------------------


async def test_the_employee_answers_and_the_claim_goes_back_for_review(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    as_: Any,
    review_requests: FakeReviewQueue,
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)
    purpose_before = (await load_claim(db_session, claim_id)).purpose

    response = await api.post(
        f"/claims/{claim_id}/answer",
        json={
            "message": "Two of us: me and J. Weber from Meridian Health.",
            "attendees": ATTENDEES,
            "purpose": purpose_before,  # sent unchanged: not an earlier value
        },
        headers=as_(),
    )

    assert response.status_code == 201, response.text
    assert response.json()["changed_fields"] == {"attendees": []}
    claim = await load_claim(db_session, claim_id)
    assert claim.status is S.EXTRACTED
    assert claim.attendees == ATTENDEES
    [answer] = await list_answers(db_session, claim_id)
    assert answer.message == "Two of us: me and J. Weber from Meridian Health."
    assert answer.changed_fields == {"attendees": []}
    [decision] = await list_decisions(db_session, claim_id)
    assert answer.reviewer_decision_id == decision.id
    assert review_requests.requested == [claim_id]


async def test_an_answer_can_add_a_preapproval_reference(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str], as_: Any
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)

    response = await api.post(
        f"/claims/{claim_id}/answer",
        json={"message": "Approved by my manager.", "preapproval_ref": "PA-2026-114"},
        headers=as_(),
    )

    assert response.status_code == 201
    assert response.json()["changed_fields"] == {"preapproval_ref": None}
    assert (await load_claim(db_session, claim_id)).preapproval_ref == "PA-2026-114"


@pytest.mark.parametrize(("sub", "role"), [("employee-2", "employee"), ("reviewer-2", "reviewer")])
async def test_only_the_claims_owner_can_answer(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    as_: Any,
    sub: str,
    role: str,
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)

    response = await api.post(
        f"/claims/{claim_id}/answer", json={"message": "Not my claim."}, headers=as_(sub, role)
    )

    assert response.status_code == 404
    assert (await load_claim(db_session, claim_id)).status is S.NEEDS_INFO


@pytest.mark.parametrize("status", [S.IN_REVIEW, S.APPROVED, S.EXTRACTED])
async def test_only_a_needs_info_claim_can_be_answered(
    api: AsyncClient, db_session: AsyncSession, as_: Any, status: S
) -> None:
    claim_id = await extracted_claim(db_session, "D04", status=status)

    response = await api.post(
        f"/claims/{claim_id}/answer", json={"message": "Here you go."}, headers=as_()
    )

    assert response.status_code == 409


async def test_a_request_is_answered_once(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    as_: Any,
    review_requests: FakeReviewQueue,
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)
    first = await api.post(f"/claims/{claim_id}/answer", json={"message": "One."}, headers=as_())

    second = await api.post(f"/claims/{claim_id}/answer", json={"message": "Two."}, headers=as_())

    assert first.status_code == 201
    assert second.status_code == 409
    assert len(await list_answers(db_session, claim_id)) == 1
    assert review_requests.requested == [claim_id]


async def test_an_answer_succeeds_when_the_review_request_cannot_be_queued(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    as_: Any,
    review_requests: FakeReviewQueue,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.review.queue.REVIEW_REQUEST_BACKOFF_SECONDS", 0)
    claim_id = await create_needs_info_claim(db_session, api, reviewer)
    review_requests.request_error = RuntimeError("SQS unavailable")

    with caplog.at_level(logging.ERROR, logger="app.review.queue"):
        response = await api.post(
            f"/claims/{claim_id}/answer", json={"message": "Attendees added."}, headers=as_()
        )

    assert response.status_code == 201
    assert (await load_claim(db_session, claim_id)).status is S.EXTRACTED
    assert f"the review request for claim {claim_id} could not be queued" in caplog.messages


async def test_the_agent_reviews_the_answered_claim_and_the_reviewer_decides_again(
    api: AsyncClient,
    db_session: AsyncSession,
    reviewer: dict[str, str],
    as_: Any,
    notification_service: FakeNotificationService,
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)
    answer = "Two of us: me and J. Weber from Meridian Health."
    await api.post(
        f"/claims/{claim_id}/answer",
        json={"message": answer, "attendees": ATTENDEES},
        headers=as_(),
    )

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db_session

    approve = ValidProposal(
        ReviewProposal.model_validate(proposal_input("approve")), ["2.2"], MODEL
    )
    agent = FakeAgent(approve)
    worker = ReviewWorker(
        ReviewWorkerSettings(), FakeReviewQueue(), sessions, agent, FakeNotificationService()
    )
    await worker.handle_message(ReviewMessage("handle-1", claim_id, 1))

    [reviewed] = agent.reviewed
    assert reviewed.attendees == ATTENDEES
    [asked] = reviewed.answered_requests
    assert asked.missing_information == ATTENDEES_MISSING
    assert asked.reviewer_comment == "Please list the attendees."
    assert asked.employee_answer == answer
    assert (await load_claim(db_session, claim_id)).status is S.IN_REVIEW

    response = await api.post(
        f"/claims/{claim_id}/decision", json={"decision": "approve"}, headers=reviewer
    )

    assert response.status_code == 201, response.text
    assert (await load_claim(db_session, claim_id)).status is S.APPROVED
    assert [sent.status for sent in notification_service.sent] == [S.NEEDS_INFO, S.APPROVED]


# --- review history ---------------------------------------------------------------------------


async def test_the_review_history_lists_every_round_newest_first(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str], as_: Any
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)
    await api.post(f"/claims/{claim_id}/answer", json={"message": "Added."}, headers=as_())
    await add_proposal(db_session, claim_id, "approve")
    await transition(db_session, claim_id, S.IN_REVIEW)
    await db_session.commit()

    response = await api.get(f"/claims/{claim_id}/review", headers=reviewer)

    assert response.status_code == 200
    latest, first = response.json()["rounds"]
    assert latest["proposal"]["decision"] == "approve"
    assert latest["decision"] is None
    assert first["proposal"]["missing_information"] == ATTENDEES_MISSING
    assert first["decision"]["comment"] == "Please list the attendees."
    assert first["answer"]["message"] == "Added."


async def test_the_employee_sees_decisions_and_answers_but_not_the_proposals(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str], as_: Any
) -> None:
    claim_id = await create_needs_info_claim(db_session, api, reviewer)

    own = await api.get(f"/claims/{claim_id}/review", headers=as_())
    other = await api.get(f"/claims/{claim_id}/review", headers=as_("employee-2"))

    assert own.status_code == 200
    [round_] = own.json()["rounds"]
    assert round_["proposal"] is None
    assert round_["decision"]["comment"] == "Please list the attendees."
    assert other.status_code == 404


async def test_a_reviewer_does_not_see_the_proposals_on_their_own_claim(
    api: AsyncClient, db_session: AsyncSession, reviewer: dict[str, str]
) -> None:
    claim_id = await create_claim_in_review(db_session, employee_sub=REVIEWER)

    response = await api.get(f"/claims/{claim_id}/review", headers=reviewer)

    assert response.status_code == 200
    [round_] = response.json()["rounds"]
    assert round_["proposal"] is None

import logging
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser
from app.auth.roles import Role
from app.claims.models import Claim
from app.claims.service import ClaimNotFoundError, InvalidTransitionError, get_claim, transition
from app.claims.status import ClaimStatus
from app.notifications.queue import ClaimNotification, NotifiedStatus, build_notification
from app.review.claim_data import load_expense, with_corrections
from app.review.models import ClaimAnswer, Decision, Proposal, ReviewerDecision
from app.review.schemas import (
    AnswerCreate,
    AnswerRead,
    ClaimReview,
    DecisionCreate,
    ProposalRead,
    ReviewerDecisionRead,
    ReviewRound,
)

logger = logging.getLogger(__name__)

DECIDED_STATUS: dict[Decision, NotifiedStatus] = {
    Decision.APPROVE: ClaimStatus.APPROVED,
    Decision.REJECT: ClaimStatus.REJECTED,
    Decision.NEEDS_INFO: ClaimStatus.NEEDS_INFO,
}
COMMENT_REQUIRED_DECISIONS = frozenset({Decision.REJECT, Decision.NEEDS_INFO})


class OwnClaimError(Exception):
    """A reviewer tried to decide a claim they submitted."""


class CommentRequiredError(Exception):
    """The decision differs from the proposal or is reject or needs_info, and has no comment."""


class InvalidCorrectionsError(Exception):
    """The extraction with the corrections laid over it is not a valid expense."""


async def decide_claim(
    session: AsyncSession, reviewer: CurrentUser, claim_id: uuid.UUID, data: DecisionCreate
) -> tuple[ReviewerDecision, ClaimNotification]:
    claim = await _lock_claim(session, claim_id)
    if claim is None:
        raise ClaimNotFoundError(claim_id)
    if claim.employee_sub == reviewer.sub:
        raise OwnClaimError(claim_id)
    target_status = DECIDED_STATUS[data.decision]
    proposal = await _find_undecided_proposal(session, claim_id)
    if claim.status is not ClaimStatus.IN_REVIEW or proposal is None:
        raise InvalidTransitionError(claim.status, target_status)
    differs = data.decision != proposal.decision
    if (differs or data.decision in COMMENT_REQUIRED_DECISIONS) and not data.comment:
        raise CommentRequiredError(claim_id)
    corrections = data.corrected_fields
    corrected_fields = corrections.dump_corrected_fields() if corrections else None
    if corrected_fields:
        await _check_corrections(session, claim_id, corrected_fields)

    decision = ReviewerDecision(
        proposal_id=proposal.id,
        reviewer_sub=reviewer.sub,
        decision=data.decision,
        comment=data.comment or None,
        corrected_fields=corrected_fields,
    )
    session.add(decision)
    await session.flush()
    await transition(session, claim_id, target_status)
    notification = build_notification(claim, target_status, comment=decision.comment)
    await session.commit()
    return decision, notification


async def answer_claim(
    session: AsyncSession, employee: CurrentUser, claim_id: uuid.UUID, data: AnswerCreate
) -> ClaimAnswer:
    claim = await _lock_claim(session, claim_id, owner=employee.sub)
    if claim is None:
        raise ClaimNotFoundError(claim_id)
    reviewer_decision = await _find_unanswered_request(session, claim_id)
    if claim.status is not ClaimStatus.NEEDS_INFO or reviewer_decision is None:
        raise InvalidTransitionError(claim.status, ClaimStatus.EXTRACTED)

    earlier_values: dict[str, Any] = {}
    for name, value in data.dump_claim_changes().items():
        if getattr(claim, name) != value:
            earlier_values[name] = getattr(claim, name)
            setattr(claim, name, value)
    answer = ClaimAnswer(
        reviewer_decision_id=reviewer_decision.id,
        message=data.message,
        changed_fields=earlier_values,
    )
    session.add(answer)
    await session.flush()
    await transition(session, claim_id, ClaimStatus.EXTRACTED)
    await session.commit()
    return answer


async def get_claim_review(
    session: AsyncSession, user: CurrentUser, claim_id: uuid.UUID
) -> ClaimReview:
    claim = await get_claim(session, user, claim_id)  # 404 unless the user may see the claim
    proposals = await session.scalars(
        select(Proposal)
        .where(Proposal.claim_id == claim_id)
        .options(selectinload(Proposal.reviewer_decision).selectinload(ReviewerDecision.answer))
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
    )
    shows_proposals = user.role is Role.REVIEWER and claim.employee_sub != user.sub
    rounds = []
    for proposal in proposals:
        decision = proposal.reviewer_decision
        answer = decision.answer if decision else None
        rounds.append(
            ReviewRound(
                proposal_id=proposal.id,
                proposal=ProposalRead.model_validate(proposal) if shows_proposals else None,
                decision=ReviewerDecisionRead.model_validate(decision) if decision else None,
                answer=AnswerRead.model_validate(answer) if answer else None,
            )
        )
    return ClaimReview(claim_id=claim_id, rounds=rounds)


async def _check_corrections(
    session: AsyncSession, claim_id: uuid.UUID, corrected_fields: dict[str, Any]
) -> None:
    expense = await load_expense(session, claim_id)
    if expense is None:
        raise InvalidCorrectionsError(claim_id)
    try:
        with_corrections(expense, corrected_fields)
    except ValidationError as exc:
        logger.info("corrections refused for claim %s: %s", claim_id, exc.errors())
        raise InvalidCorrectionsError(claim_id) from exc


async def _lock_claim(
    session: AsyncSession, claim_id: uuid.UUID, *, owner: str | None = None
) -> Claim | None:
    query = select(Claim).where(Claim.id == claim_id)
    if owner is not None:
        query = query.where(Claim.employee_sub == owner)
    return await session.scalar(query.with_for_update().execution_options(populate_existing=True))


async def _find_undecided_proposal(session: AsyncSession, claim_id: uuid.UUID) -> Proposal | None:
    return await session.scalar(
        select(Proposal)
        .outerjoin(ReviewerDecision, ReviewerDecision.proposal_id == Proposal.id)
        .where(Proposal.claim_id == claim_id, ReviewerDecision.id.is_(None))
    )


async def _find_unanswered_request(
    session: AsyncSession, claim_id: uuid.UUID
) -> ReviewerDecision | None:
    return await session.scalar(
        select(ReviewerDecision)
        .join(ReviewerDecision.proposal)
        .outerjoin(ClaimAnswer, ClaimAnswer.reviewer_decision_id == ReviewerDecision.id)
        .where(
            Proposal.claim_id == claim_id,
            ReviewerDecision.decision == Decision.NEEDS_INFO,
            ClaimAnswer.id.is_(None),
        )
    )

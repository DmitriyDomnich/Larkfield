import logging
import uuid

from sqlalchemy import select

from app.claims.models import Claim
from app.claims.service import ConcurrentTransitionError, InvalidTransitionError, transition
from app.claims.status import ClaimStatus
from app.core.db import SessionFactory
from app.review.agent import NoValidProposal, ReviewAgent, ValidProposal
from app.review.claim_data import load_extracted_claim
from app.review.models import Proposal

logger = logging.getLogger(__name__)

NO_VALID_PROPOSAL_REASON = (
    "The claim could not be checked against the expense policy automatically. "
    "Please submit a new claim."
)
TECHNICAL_FAILURE_REASON = (
    "The review could not be completed because of a technical problem. Please submit a new claim."
)


async def review_claim(
    sessions: SessionFactory,
    agent: ReviewAgent,
    claim_id: uuid.UUID,
    *,
    receive_count: int,
    max_receives: int,
) -> None:
    async with sessions() as session:
        claim = await load_extracted_claim(session, claim_id)
    if claim is None:
        logger.info("claim %s is not extracted; nothing to review", claim_id)
        return

    try:
        outcome = await agent.review(claim)
    except Exception:
        if receive_count < max_receives:
            raise
        logger.exception("review of claim %s failed on the last delivery", claim_id)
        await _finish_claim(sessions, claim_id, None, TECHNICAL_FAILURE_REASON)
        return

    match outcome:
        case ValidProposal():
            await _finish_claim(sessions, claim_id, outcome, None)
        case NoValidProposal(detail=detail):
            logger.warning("no valid proposal for claim %s: %s", claim_id, detail)
            await _finish_claim(sessions, claim_id, None, NO_VALID_PROPOSAL_REASON)


async def _finish_claim(
    sessions: SessionFactory,
    claim_id: uuid.UUID,
    outcome: ValidProposal | None,
    failure_reason: str | None,
) -> None:
    async with sessions() as session:
        status = await session.scalar(
            select(Claim.status).where(Claim.id == claim_id).with_for_update()
        )
        if status is not ClaimStatus.EXTRACTED:
            logger.info("claim %s is %s; another delivery finished it", claim_id, status)
            await session.rollback()
            return
        if outcome is not None:
            proposal = outcome.proposal
            session.add(
                Proposal(
                    claim_id=claim_id,
                    decision=proposal.decision,
                    reasons=[reason.model_dump() for reason in proposal.reasons],
                    missing_information=proposal.missing_information,
                    duplicate_of=proposal.duplicate_of,
                    ai_model=outcome.model,
                    retrieved_clauses=outcome.retrieved_clauses,
                )
            )
            await session.flush()
        target = ClaimStatus.FAILED if failure_reason else ClaimStatus.IN_REVIEW
        try:
            await transition(session, claim_id, target, failure_reason=failure_reason)
        except (ConcurrentTransitionError, InvalidTransitionError):
            # another delivery finished this claim first
            logger.info("claim %s already left extracted", claim_id)
            await session.rollback()
            return
        await session.commit()
    if outcome is not None:
        logger.info(
            "claim %s: proposal %s stored, citing %s; claim is in_review",
            claim_id,
            outcome.proposal.decision,
            [reason.clause_id for reason in outcome.proposal.reasons],
        )
    else:
        logger.info("claim %s: failed: %s", claim_id, failure_reason)

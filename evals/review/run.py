import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from app.review.agent import NoValidProposal, ReviewAgent, ValidProposal
from app.review.claim_data import ClaimUnderReview
from app.review.proposal import ReviewProposal
from evals.review.cases import ReviewCase, claim_for
from evals.review.history import RunHistory
from evals.review.results import CaseResult, RunResults

logger = logging.getLogger(__name__)


async def run_cases(
    agent: ReviewAgent, history: RunHistory, cases: Sequence[ReviewCase], model: str
) -> RunResults:
    """Review the cases one at a time in order; `history` is the one the agent's tools read"""
    started_at = datetime.now(UTC)
    reviewed: set[str] = set()
    results = []
    for case in cases:
        if case.process_after and case.process_after not in reviewed:
            raise ValueError(f"{case.id} must be reviewed after {case.process_after}")
        claim = claim_for(case)
        logger.info("%s (claim %s)", case.id, claim.claim_id)
        result = await review_case(agent, case.id, claim)
        if result.proposal is not None:
            history.add(claim)
        logger.info(
            "%s: %s", case.id, result.proposal.decision if result.proposal else result.failure
        )
        results.append(result)
        reviewed.add(case.id)
    return RunResults(started_at=started_at, model=model, cases=results)


async def review_case(agent: ReviewAgent, case_id: str, claim: ClaimUnderReview) -> CaseResult:
    try:
        outcome = await agent.review(claim)
    except Exception as exc:
        logger.exception("%s: the review failed", case_id)
        return CaseResult(
            case_id=case_id,
            proposal=None,
            retrieved_clauses=None,
            failure=f"error: {type(exc).__name__}",
        )
    match outcome:
        case ValidProposal():
            return CaseResult(
                case_id=case_id,
                proposal=ReviewProposal.model_validate(outcome.proposal.model_dump()),
                retrieved_clauses=outcome.retrieved_clauses,
                failure=None,
            )
        case NoValidProposal(detail=detail):
            return CaseResult(
                case_id=case_id, proposal=None, retrieved_clauses=None, failure=detail
            )

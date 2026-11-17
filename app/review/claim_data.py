import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.claims.models import Claim
from app.claims.status import ClaimStatus
from app.extraction.models import Extraction
from app.extraction.schemas import ExtractedExpense, LineItem
from app.review.models import ClaimAnswer, Decision, Proposal, ReviewerDecision


@dataclass(frozen=True)
class AnsweredRequest:

    missing_information: list[str]
    reviewer_comment: str | None
    employee_answer: str


@dataclass(frozen=True)
class ClaimUnderReview:
    claim_id: uuid.UUID
    employee_sub: str
    purpose: str
    preapproval_ref: str | None
    submitted_at: datetime
    expense: ExtractedExpense
    attendees: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    document_sha256: str | None = None
    answered_requests: list[AnsweredRequest] = field(default_factory=list)

    @property
    def days_to_submission(self) -> int:
        """Days from the document date to the submission (policy 1.2)"""
        return (self.submitted_at.astimezone(UTC).date() - self.expense.document_date).days


async def load_extracted_claim(
    session: AsyncSession, claim_id: uuid.UUID
) -> ClaimUnderReview | None:
    return await _load_claim(session, claim_id, extracted_only=True)


async def load_claim_of_any_status(
    session: AsyncSession, claim_id: uuid.UUID
) -> ClaimUnderReview | None:
    """A claim with an extraction in any status, e.g. one already reviewed"""
    return await _load_claim(session, claim_id, extracted_only=False)


async def _load_claim(
    session: AsyncSession, claim_id: uuid.UUID, *, extracted_only: bool
) -> ClaimUnderReview | None:
    claim = await session.scalar(
        select(Claim)
        .where(Claim.id == claim_id)
        .options(selectinload(Claim.document))
        .execution_options(populate_existing=True)
    )
    if claim is None or claim.document is None:
        return None
    if extracted_only and claim.status is not ClaimStatus.EXTRACTED:
        return None
    extraction = await session.scalar(
        select(Extraction)
        .where(Extraction.document_id == claim.document.id)
        .options(selectinload(Extraction.line_items))
    )
    if extraction is None:
        return None
    return ClaimUnderReview(
        claim_id=claim.id,
        employee_sub=claim.employee_sub,
        purpose=claim.purpose,
        preapproval_ref=claim.preapproval_ref,
        submitted_at=claim.submitted_at,
        expense=map_expense(extraction),
        attendees=claim.attendees,
        warnings=extraction.warnings,
        document_sha256=claim.document.sha256,
        answered_requests=await _load_answered_requests(session, claim.id),
    )


async def _load_answered_requests(
    session: AsyncSession, claim_id: uuid.UUID
) -> list[AnsweredRequest]:
    rows = await session.execute(
        select(Proposal.missing_information, ReviewerDecision.comment, ClaimAnswer.message)
        .join(ReviewerDecision, ReviewerDecision.proposal_id == Proposal.id)
        .join(ClaimAnswer, ClaimAnswer.reviewer_decision_id == ReviewerDecision.id)
        .where(Proposal.claim_id == claim_id, ReviewerDecision.decision == Decision.NEEDS_INFO)
        .order_by(Proposal.created_at, Proposal.id)
    )
    return [
        AnsweredRequest(list(missing_information), comment, message)
        for missing_information, comment, message in rows
    ]


def map_expense(extraction: Extraction) -> ExtractedExpense:
    fields = {name: getattr(extraction, name) for name in ExtractedExpense.model_fields}
    fields["line_items"] = [
        LineItem(
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=item.amount,
        )
        for item in extraction.line_items
    ]
    return ExtractedExpense.model_validate(fields)

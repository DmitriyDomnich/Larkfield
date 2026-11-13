import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import ColumnElement, and_, extract, false, or_, select, tuple_

from app.claims.models import Claim, Document
from app.claims.status import ClaimStatus
from app.core.db import SessionFactory
from app.extraction.models import ExpenseCategory, Extraction
from app.review.claim_data import ClaimUnderReview

NOT_A_PRIOR_CLAIM = (ClaimStatus.FAILED,)
NOT_SPENT = (ClaimStatus.FAILED, ClaimStatus.REJECTED)


@dataclass(frozen=True)
class PossibleClaimDuplicate:
    claim_id: uuid.UUID
    vendor_name: str
    vendor_tax_id: str | None
    document_number: str | None
    document_date: date
    total: Decimal
    currency: str
    status: str
    same_employee: bool
    same_file: bool


@dataclass(frozen=True)
class TrainingClaim:
    claim_id: uuid.UUID
    document_date: date
    total: Decimal
    currency: str
    status: str


class ClaimsHistory(Protocol):
    async def find_possible_duplicates(
        self, claim: ClaimUnderReview
    ) -> list[PossibleClaimDuplicate]: ...

    async def list_training_claims(self, claim: ClaimUnderReview) -> list[TrainingClaim]: ...


class DatabaseClaimsHistory:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def find_possible_duplicates(
        self, claim: ClaimUnderReview
    ) -> list[PossibleClaimDuplicate]:
        """Find duplicate claims to handle policy 1.4 (Duplicates)"""
        expense = claim.expense
        same_expense = and_(
            Extraction.document_date == expense.document_date,
            Extraction.total == expense.total,
            Extraction.currency == expense.currency,
        )
        same_file = Document.sha256 == claim.document_sha256
        matches = or_(same_expense, same_file) if claim.document_sha256 else same_expense
        query = (
            select(
                Claim.id.label("claim_id"),
                Extraction.vendor_name,
                Extraction.vendor_tax_id,
                Extraction.document_number,
                Extraction.document_date,
                Extraction.total,
                Extraction.currency,
                Claim.status,
                (Claim.employee_sub == claim.employee_sub).label("same_employee"),
                (same_file if claim.document_sha256 else false()).label("same_file"),
            )
            .join(Document, Document.claim_id == Claim.id)
            .join(Extraction, Extraction.document_id == Document.id)
            .where(
                matches,
                Claim.status.not_in(NOT_A_PRIOR_CLAIM),
                _submitted_before(claim),
            )
            .order_by(Claim.submitted_at)
        )
        async with self._sessions() as session:
            rows = await session.execute(query)
            return [PossibleClaimDuplicate(**row._asdict()) for row in rows]

    async def list_training_claims(self, claim: ClaimUnderReview) -> list[TrainingClaim]:
        """Find employee's earlier training claims in the document's calendar year (policy 5.1)"""
        query = (
            select(
                Claim.id.label("claim_id"),
                Extraction.document_date,
                Extraction.total,
                Extraction.currency,
                Claim.status,
            )
            .join(Document, Document.claim_id == Claim.id)
            .join(Extraction, Extraction.document_id == Document.id)
            .where(
                Claim.employee_sub == claim.employee_sub,
                Extraction.category == ExpenseCategory.TRAINING,
                extract("year", Extraction.document_date) == claim.expense.document_date.year,
                Claim.status.not_in(NOT_SPENT),
                _submitted_before(claim),
            )
            .order_by(Extraction.document_date)
        )
        async with self._sessions() as session:
            rows = await session.execute(query)
            return [TrainingClaim(**row._asdict()) for row in rows]


def _submitted_before(claim: ClaimUnderReview) -> ColumnElement[bool]:
    return tuple_(Claim.submitted_at, Claim.id) < tuple_(claim.submitted_at, claim.claim_id)

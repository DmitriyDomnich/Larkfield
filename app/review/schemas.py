import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.claims.schemas import Attendee
from app.extraction.models import DocumentType, ExpenseCategory
from app.extraction.schemas import LineItem, Money
from app.review.models import Decision
from app.review.proposal import Reason

Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


NOT_NULLABLE_EXPENSE_FIELDS = frozenset(
    {
        "document_type",
        "vendor_name",
        "document_date",
        "currency",
        "line_items",
        "total",
        "category",
    }
)


class ExpenseCorrections(BaseModel):
    """Partial ExtractedExpense: only the fields the reviewer corrected"""

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType | None = None
    vendor_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = (
        None
    )
    vendor_tax_id: Annotated[str, StringConstraints(max_length=64)] | None = None
    document_number: Annotated[str, StringConstraints(max_length=128)] | None = None
    document_date: date | None = None
    document_time: time | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    line_items: list[LineItem] | None = None
    subtotal: Money | None = None
    tax_amount: Money | None = None
    tip_amount: Money | None = None
    total: Annotated[Money, Field(gt=0)] | None = None
    category: ExpenseCategory | None = None

    @model_validator(mode="after")
    def _required_fields_are_not_cleared(self) -> Self:
        cleared = sorted(
            name
            for name in self.model_fields_set & NOT_NULLABLE_EXPENSE_FIELDS
            if getattr(self, name) is None
        )
        if cleared:
            raise ValueError(f"these fields cannot be null: {', '.join(cleared)}")
        return self

    def dump_corrected_fields(self) -> dict[str, Any] | None:
        return self.model_dump(mode="json", exclude_unset=True) or None


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    comment: Comment | None = Field(
        default=None,
        description=(
            "Required for reject and needs_info, and when the decision differs from the proposal"
        ),
    )
    corrected_fields: ExpenseCorrections | None = None


class ReviewerDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    proposal_id: uuid.UUID
    reviewer_sub: str
    decision: Decision
    comment: str | None
    corrected_fields: dict[str, Any] | None
    created_at: datetime


class AnswerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    purpose: Annotated[str, StringConstraints(min_length=10, max_length=500)] | None = None
    attendees: Annotated[list[Attendee], Field(max_length=50)] | None = None
    preapproval_ref: Annotated[str, StringConstraints(pattern=r"^PA-[0-9]{4}-[0-9]{3}$")] | None = (
        None
    )

    @model_validator(mode="after")
    def _purpose_and_attendees_are_not_cleared(self) -> Self:
        for name in ("purpose", "attendees"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def dump_claim_changes(self) -> dict[str, Any]:
        return self.model_dump(mode="json", include=self.model_fields_set - {"message"})


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reviewer_decision_id: uuid.UUID
    message: str
    changed_fields: dict[str, Any]
    created_at: datetime


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    decision: Decision
    reasons: list[Reason]
    missing_information: list[str]
    duplicate_of: uuid.UUID | None
    ai_model: str
    retrieved_clauses: list[str]
    created_at: datetime


class ReviewRound(BaseModel):
    proposal_id: uuid.UUID
    proposal: ProposalRead | None
    decision: ReviewerDecisionRead | None
    answer: AnswerRead | None


class ClaimReview(BaseModel):
    claim_id: uuid.UUID
    rounds: list[ReviewRound] = Field(description="Newest first")

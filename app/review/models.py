import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.claims.models import Claim
from app.core.models import Base, CreatedAtMixin, one_of, str_enum


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_INFO = "needs_info"


class Proposal(CreatedAtMixin, Base):
    """The review agent's proposal. Append-only: a trigger refuses UPDATE, and a re-run after
    needs_info adds a new row."""

    __tablename__ = "proposals"
    __table_args__ = (
        one_of("decision", Decision),
        CheckConstraint(
            "jsonb_typeof(reasons) = 'array' AND jsonb_array_length(reasons) >= 1",
            name="reasons_not_empty",
        ),
        CheckConstraint(
            "jsonb_typeof(missing_information) = 'array' AND "
            "(decision = 'needs_info') = (jsonb_array_length(missing_information) > 0)",
            name="missing_information_iff_needs_info",
        ),
        CheckConstraint("duplicate_of <> claim_id", name="duplicate_of_other_claim"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), index=True)
    decision: Mapped[Decision] = mapped_column(str_enum(Decision))
    # [{clause_id, quote, explanation}]
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    missing_information: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    # Set when policy 1.4 (duplicate claim) applies
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    # Bedrock model name
    ai_model: Mapped[str] = mapped_column(String(255))

    claim: Mapped[Claim] = relationship(foreign_keys=[claim_id], lazy="raise")
    reviewer_decision: Mapped["ReviewerDecision | None"] = relationship(
        back_populates="proposal", lazy="raise"
    )


class ReviewerDecision(CreatedAtMixin, Base):
    """The finance reviewer's final decision on one proposal"""

    __tablename__ = "reviewer_decisions"
    __table_args__ = (
        one_of("decision", Decision),
        CheckConstraint(
            "decision <> 'needs_info' OR btrim(coalesce(comment, '')) <> ''",
            name="comment_required_for_needs_info",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id"), unique=True)
    # user id
    reviewer_sub: Mapped[str] = mapped_column(String(255), index=True)
    decision: Mapped[Decision] = mapped_column(str_enum(Decision))
    comment: Mapped[str | None] = mapped_column(Text)
    # Partial ExtractedExpense: only the fields the reviewer corrected.
    corrected_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    proposal: Mapped[Proposal] = relationship(back_populates="reviewer_decision", lazy="raise")

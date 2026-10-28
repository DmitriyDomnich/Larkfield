import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.claims.status import INITIAL_STATUS, ClaimStatus
from app.core.models import Base, CreatedAtMixin, TimestampMixin, str_enum


class ClaimStatusRow(Base):
    """Lookup table of statuses; seeded by migrations."""

    __tablename__ = "claim_statuses"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)


class ClaimStatusTransition(Base):
    """Allowed (from, to) pairs. A trigger on `claims` refuses any status change not listed here."""

    __tablename__ = "claim_status_transitions"

    from_status: Mapped[str] = mapped_column(
        String(32), ForeignKey("claim_statuses.code"), primary_key=True
    )
    to_status: Mapped[str] = mapped_column(
        String(32), ForeignKey("claim_statuses.code"), primary_key=True
    )


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("char_length(purpose) BETWEEN 10 AND 500", name="purpose_length"),
        CheckConstraint(
            "preapproval_ref ~ '^PA-[0-9]{4}-[0-9]{3}$'", name="preapproval_ref_format"
        ),
        CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)", name="failure_reason_iff_failed"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    # user id
    employee_sub: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(Text)
    attendees: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    preapproval_ref: Mapped[str | None] = mapped_column(String(11))
    status: Mapped[ClaimStatus] = mapped_column(
        str_enum(ClaimStatus),
        ForeignKey("claim_statuses.code"),
        server_default=INITIAL_STATUS.value,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped["Document | None"] = relationship(back_populates="claim", lazy="raise")


class Document(CreatedAtMixin, Base):
    """The uploaded file. One per claim."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), unique=True)
    s3_key: Mapped[str] = mapped_column(String(1024), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))

    claim: Mapped[Claim] = relationship(back_populates="document", lazy="raise")

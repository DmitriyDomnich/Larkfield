import uuid
from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, CreatedAtMixin, one_of, str_enum

MONEY = Numeric(12, 2)


class DocumentType(StrEnum):
    RECEIPT = "receipt"
    INVOICE = "invoice"
    CARD_SLIP = "card_slip"


class ExpenseCategory(StrEnum):
    MEAL = "meal"
    CLIENT_ENTERTAINMENT = "client_entertainment"
    TEAM_MEAL = "team_meal"
    AIR_TRAVEL = "air_travel"
    RAIL_TRAVEL = "rail_travel"
    TAXI = "taxi"
    MILEAGE = "mileage"
    HOTEL = "hotel"
    EQUIPMENT = "equipment"
    SOFTWARE = "software"
    ACCESSORIES = "accessories"
    TRAINING = "training"
    CONFERENCE = "conference"
    FINE = "fine"
    OTHER = "other"


class Extraction(CreatedAtMixin, Base):
    """A validated ExtractedExpense for one document"""

    __tablename__ = "extractions"
    __table_args__ = (
        one_of("document_type", DocumentType),
        one_of("category", ExpenseCategory),
        CheckConstraint("btrim(vendor_name) <> ''", name="vendor_name_not_empty"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("total > 0", name="total_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    document_type: Mapped[DocumentType] = mapped_column(str_enum(DocumentType))
    vendor_name: Mapped[str] = mapped_column(Text)
    vendor_tax_id: Mapped[str | None] = mapped_column(String(64))
    document_number: Mapped[str | None] = mapped_column(String(128))
    document_date: Mapped[date] = mapped_column(Date)
    document_time: Mapped[time | None] = mapped_column(Time)
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(MONEY)
    tax_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    tip_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    total: Mapped[Decimal] = mapped_column(MONEY)
    category: Mapped[ExpenseCategory] = mapped_column(str_enum(ExpenseCategory))
    # Failed sanity checks (sum, future date, unknown currency), shown to the reviewer.
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    # Bedrock model name
    ai_model: Mapped[str] = mapped_column(String(255))

    line_items: Mapped[list["ExtractionLineItem"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        order_by="ExtractionLineItem.position",
        lazy="raise",
    )


class ExtractionLineItem(Base):
    __tablename__ = "extraction_line_items"
    __table_args__ = (
        UniqueConstraint("extraction_id", "position"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    amount: Mapped[Decimal] = mapped_column(MONEY)

    extraction: Mapped[Extraction] = relationship(back_populates="line_items", lazy="raise")

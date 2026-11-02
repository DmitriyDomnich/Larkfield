from datetime import date, time
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.extraction.models import DocumentType, ExpenseCategory

Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]

SUM_TOLERANCE = Decimal("0.02")

# ISO 4217 active codes, to validate if currency is valid
_ISO_4217_CODES = """
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN
BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN
ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD
JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT
MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG
QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT
TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF XCD XCG XOF
XPF YER ZAR ZMW ZWG
"""
ISO_4217 = frozenset(_ISO_4217_CODES.split())


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    quantity: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]
    unit_price: Annotated[Decimal, Field(max_digits=12, decimal_places=4)] | None
    amount: Money


class ExtractedExpense(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    vendor_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    vendor_tax_id: Annotated[str, StringConstraints(max_length=64)] | None
    document_number: Annotated[str, StringConstraints(max_length=128)] | None
    document_date: date
    document_time: time | None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    line_items: list[LineItem]
    subtotal: Money | None
    tax_amount: Money | None
    tip_amount: Money | None
    total: Annotated[Money, Field(gt=0)]
    category: ExpenseCategory

    @model_validator(mode="after")
    def _items_only_missing_on_card_slip(self) -> Self:
        if not self.line_items and self.document_type != DocumentType.CARD_SLIP:
            raise ValueError("line_items may be empty only for a card_slip")
        return self


class ExpenseWarning(BaseModel):
    """A failed check on a valid extraction, shown to the reviewer"""

    code: Literal["sum_mismatch", "future_date", "unknown_currency"]
    message: str


def items_include_tax(expense: ExtractedExpense) -> bool:
    """True when the item amounts already contain the tax (gross prices)"""
    gross = sum((i.amount for i in expense.line_items), Decimal(0)) + (expense.tip_amount or 0)
    return abs(gross - expense.total) <= SUM_TOLERANCE


def expense_warnings(expense: ExtractedExpense, today: date) -> list[ExpenseWarning]:
    warnings: list[ExpenseWarning] = []
    # A card slip has no items
    if expense.line_items and not items_include_tax(expense):
        items = sum((i.amount for i in expense.line_items), Decimal(0))
        net = items + (expense.tax_amount or 0) + (expense.tip_amount or 0)
        if abs(net - expense.total) > SUM_TOLERANCE:
            warnings.append(
                ExpenseWarning(
                    code="sum_mismatch",
                    message=f"Items, tax and tip add up to {net}, the total is {expense.total}",
                )
            )
    if expense.document_date > today:
        warnings.append(
            ExpenseWarning(
                code="future_date",
                message=f"Document date {expense.document_date} is in the future",
            )
        )
    if expense.currency not in ISO_4217:
        warnings.append(
            ExpenseWarning(
                code="unknown_currency",
                message=f"{expense.currency} is not an ISO 4217 currency",
            )
        )
    return warnings

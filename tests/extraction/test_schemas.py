from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.extraction.schemas import ExtractedExpense, expense_warnings

TODAY = date(2026, 10, 30)


def receipt(**changes: Any) -> dict[str, Any]:
    """Gross prices: items add up to the total, tax is contained in them"""
    data: dict[str, Any] = {
        "document_type": "receipt",
        "vendor_name": "Brauhaus am Markt",
        "vendor_tax_id": "DE123456789",
        "document_number": "R-20481",
        "document_date": "2026-09-03",
        "document_time": "12:41",
        "currency": "EUR",
        "line_items": [
            {"description": "Tagessuppe", "quantity": "1", "unit_price": "6.50", "amount": "6.50"},
            {
                "description": "Käsespätzle",
                "quantity": "2",
                "unit_price": "6.00",
                "amount": "12.00",
            },
        ],
        "subtotal": "15.55",
        "tax_amount": "2.95",
        "tip_amount": None,
        "total": "18.50",
        "category": "meal",
    }
    return data | changes


def invoice(**changes: Any) -> dict[str, Any]:
    """Net lines with tax added: items + tax = total"""
    line = {"description": "Plan", "quantity": "1", "unit_price": "24.37", "amount": "24.37"}
    base = {"document_type": "invoice", "line_items": [line], "subtotal": "24.37"}
    return receipt(**base, tax_amount="4.63", total="29.00", category="software") | changes


def test_valid_receipt_loads_money_as_decimal() -> None:
    expense = ExtractedExpense.model_validate(receipt())

    assert expense.total == Decimal("18.50")
    assert isinstance(expense.line_items[1].quantity, Decimal)
    assert expense.document_date == date(2026, 9, 3)


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"document_type": "ticket"}, id="unknown-document-type"),
        pytest.param({"category": "books"}, id="unknown-category"),
        pytest.param({"currency": "eur"}, id="lowercase-currency"),
        pytest.param({"currency": "EURO"}, id="four-letter-currency"),
        pytest.param({"total": "0"}, id="zero-total"),
        pytest.param({"total": "-5.00"}, id="negative-total"),
        pytest.param({"vendor_name": "  "}, id="blank-vendor"),
        pytest.param({"line_items": []}, id="receipt-without-items"),
        pytest.param({"total": "18.505"}, id="three-decimal-money"),
        pytest.param({"confidence": "high"}, id="unknown-field"),
        pytest.param(
            {
                "line_items": [
                    {"description": "x", "quantity": "0", "unit_price": None, "amount": "1"}
                ]
            },
            id="zero-quantity",
        ),
    ],
)
def test_contract_rules_are_enforced(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ExtractedExpense.model_validate(receipt(**changes))


def test_card_slip_may_have_no_items() -> None:
    slip = receipt(document_type="card_slip", line_items=[], subtotal=None, tax_amount=None)

    expense = ExtractedExpense.model_validate(slip)

    assert expense.line_items == []
    assert expense_warnings(expense, TODAY) == []


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(receipt(), id="tax-included-in-items"),
        pytest.param(invoice(), id="tax-added-to-items"),
        pytest.param(receipt(tip_amount="1.85", total="20.35"), id="tip-on-top"),
        pytest.param(receipt(total="18.52"), id="within-two-cents"),
        pytest.param(receipt(tax_amount=None, subtotal=None), id="no-tax-printed"),
    ],
)
def test_amounts_that_add_up_give_no_warning(data: dict[str, Any]) -> None:
    assert expense_warnings(ExtractedExpense.model_validate(data), TODAY) == []


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(receipt(total="18.53"), id="three-cents-off"),
        pytest.param(invoice(tax_amount="4.00"), id="wrong-tax"),
        pytest.param(receipt(tip_amount="2.00"), id="tip-missing-from-total"),
    ],
)
def test_amounts_that_do_not_add_up_warn(data: dict[str, Any]) -> None:
    warnings = expense_warnings(ExtractedExpense.model_validate(data), TODAY)

    assert [w.code for w in warnings] == ["sum_mismatch"]


def test_future_document_date_warns() -> None:
    expense = ExtractedExpense.model_validate(receipt(document_date="2026-10-31"))

    assert [w.code for w in expense_warnings(expense, TODAY)] == ["future_date"]
    assert expense_warnings(expense, date(2026, 10, 31)) == []


def test_unknown_currency_warns_but_is_valid() -> None:
    expense = ExtractedExpense.model_validate(receipt(currency="XYZ"))

    assert [w.code for w in expense_warnings(expense, TODAY)] == ["unknown_currency"]

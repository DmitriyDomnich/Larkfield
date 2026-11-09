from datetime import UTC, datetime
from decimal import Decimal

from app.extraction.schemas import ExtractedExpense
from evals.extraction.models import DocumentResult, TokenUsage
from evals.extraction.pricing import ModelPrice
from evals.extraction.report import (
    RunInfo,
    mismatches,
    render_markdown,
    summarize,
)
from evals.extraction.scoring import SCORED_FIELDS, score_fields
from tests.extraction.fakes import expense, label

INFO = RunInfo(datetime(2026, 11, 5, 14, 2, tzinfo=UTC), "eu.model", 4, Decimal("0.05"))
LABELS = {"D01": expense("D01"), "D02": expense("D02")}


PRICE = ModelPrice(input_per_mtok=Decimal(3), output_per_mtok=Decimal(15))


def extracted(
    doc_id: str, actual: ExtractedExpense, latency_s: float, attempts: int = 1
) -> DocumentResult:
    return DocumentResult(
        doc_id,
        "extracted",
        None,
        actual,
        score_fields(LABELS[doc_id], actual),
        latency_s,
        TokenUsage(4000, 600, attempts),
    )


def results() -> list[DocumentResult]:
    items = label("D01")["line_items"]
    wrong_items = [*items[:2], items[2] | {"amount": "8.30"}]
    wrong_d01 = expense("D01", vendor_name="Brauhaus | am Markt", line_items=wrong_items)
    unreadable_e10 = DocumentResult(
        "E10", "unreadable", "Total cut off", None, None, 1.0, TokenUsage(3000, 100, 1)
    )
    return [
        extracted("D01", wrong_d01, 2.0, attempts=2),
        extracted("D02", expense("D02"), 4.0),
        unreadable_e10,
    ]


def test_summary_counts_fields_documents_cost_and_latency() -> None:
    summary = summarize(results(), PRICE)

    assert summary.labelled == 2
    assert summary.fully_correct == 1
    assert summary.field_correct["vendor_name"] == 1
    assert summary.field_correct["total"] == 2
    assert list(summary.field_correct) == list(SCORED_FIELDS)
    assert summary.unlabelled_passed == {"E10": True}
    # (11000 * 3 + 1300 * 15) / 1e6
    assert summary.total_cost == Decimal("0.0525")
    assert summary.cost_per_document == Decimal("0.0175")
    assert (summary.latency_p50_s, summary.latency_p95_s) == (2.0, 4.0)


def test_summary_without_results_has_no_latency() -> None:
    summary = summarize([], PRICE)

    assert summary.latency_p95_s is None
    assert summary.cost_per_document == 0


def test_mismatches_show_the_wrong_field_and_the_differing_items() -> None:
    rows = mismatches(results(), LABELS)

    assert rows == [
        ("D01", "vendor_name", "Brauhaus am Markt", "Brauhaus \\| am Markt"),
        (
            "D01",
            "line_items",
            "3 items",
            "3 items<br>amount differs on 1: Käsespätzle: 8.20 vs 8.30",
        ),
    ]


def test_items_without_a_partner_are_missing_or_unexpected() -> None:
    items = label("D01")["line_items"]
    renamed = [items[0] | {"description": "Tagesuppe"}, *items[1:], items[1]]
    result = extracted("D01", expense("D01", line_items=renamed), 1.0)

    [(_, field, expected, got)] = mismatches([result], LABELS)

    assert (field, expected) == ("line_items", "3 items")
    assert got == "4 items<br>missing 1: Tagessuppe<br>unexpected 2: Tagesuppe; Apfelschorle"


def test_many_differing_items_show_three_examples() -> None:
    items = [
        {"description": f"Item {n}", "quantity": "2", "unit_price": "1.00", "amount": "2.00"}
        for n in range(5)
    ]
    label_e = expense("D01", line_items=items, subtotal=None, tax_amount=None)
    got_e = expense("D01", line_items=[i | {"unit_price": None} for i in items])
    result = DocumentResult(
        "D01", "extracted", None, got_e, score_fields(label_e, got_e), 1.0, TokenUsage()
    )

    [row] = [r for r in mismatches([result], {"D01": label_e}) if r[1] == "line_items"]

    assert row[3] == (
        "5 items<br>unit_price differs on 5: Item 0: 1.00 vs null; Item 1: 1.00 vs null; "
        "Item 2: 1.00 vs null; and 2 more"
    )


def test_markdown_report_has_every_section() -> None:
    summary = summarize(results(), PRICE)

    markdown = render_markdown(results(), LABELS, summary, INFO, PRICE)

    assert "# Extraction eval — 2026-11-05 14:02 UTC" in markdown
    assert "| Documents with every field correct | 1/2 (50.0%) |" in markdown
    assert "| E10 failed with a reason | yes |" in markdown
    assert "| Cost per document | $0.017500 |" in markdown
    assert "| Latency p50 / p95 | 2.0 s / 4.0 s |" in markdown
    assert "| vendor_name | 1/2 (50.0%) |" in markdown
    assert "| D01 | vendor_name | Brauhaus am Markt |" in markdown
    assert "| D01 | extracted | 11/13 (84.6%) | 2 | 2.0 s |" in markdown
    assert "| Documents needing more than one attempt | 1 |" in markdown
    e10_row = "| E10 | unreadable | - | 1 | 1.0 s | 3000 / 100 | $0.010500 | Total cut off |"
    assert e10_row in markdown

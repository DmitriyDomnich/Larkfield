from collections import Counter
from decimal import Decimal

import pypdfium2 as pdfium
import pytest

from evals.generator.build import content, render, render_pdf
from evals.generator.photo import read_source_fingerprint, source_fingerprint
from evals.generator.render import RENDER
from tests.evals.docs import PDF_IDS, PHOTO_IDS, document_path


def pdf_text(pdf: bytes) -> str:
    """All text of the PDF, lowercased and without whitespace, so wrapping does not matter"""
    document = pdfium.PdfDocument(pdf)
    try:
        text = "".join(page.get_textpage().get_text_range() for page in document)
    finally:
        document.close()
    return "".join(text.split()).casefold()


def squash(text: str) -> str:
    return "".join(text.split()).casefold()


@pytest.mark.parametrize("doc_id", PDF_IDS)
def test_committed_pdf_is_what_its_label_generates(doc_id: str) -> None:
    """Fails when a label or render setting changed without `make eval-docs`"""
    assert render_pdf(doc_id) == document_path(doc_id).read_bytes()


@pytest.mark.parametrize("doc_id", sorted(PHOTO_IDS))
def test_committed_photo_is_what_its_label_generates(doc_id: str) -> None:
    """Compares the photo's source: the source PDF renders the same everywhere"""
    photo = RENDER[doc_id].photo
    assert photo is not None

    expected = source_fingerprint(render_pdf(doc_id), photo)

    assert read_source_fingerprint(document_path(doc_id).read_bytes()) == expected


def test_a_label_change_makes_the_photo_stale() -> None:
    photo = RENDER["E06"].photo
    assert photo is not None
    label = content("E06")
    item = label.line_items[0]
    changed = label.model_copy(
        update={
            "line_items": [
                item.model_copy(update={"amount": item.amount + 1}),
                *label.line_items[1:],
            ],
            "total": label.total + 1,
        }
    )

    committed = read_source_fingerprint(document_path("E06").read_bytes())

    assert source_fingerprint(render_pdf("E06", changed), photo) != committed


@pytest.mark.parametrize("doc_id", PDF_IDS)
def test_pdf_shows_the_label_values(doc_id: str) -> None:
    expense = content(doc_id)
    spec = RENDER[doc_id]
    text = pdf_text(document_path(doc_id).read_bytes())

    assert squash(expense.vendor_name) in text
    if expense.document_number:
        assert squash(expense.document_number) in text
    assert squash(spec.date(expense.document_date)) in text
    assert squash(spec.money(expense.total)) in text
    for item in expense.line_items:
        assert squash(item.description) in text
        assert squash(spec.money(item.amount)) in text


def test_a_label_change_changes_the_document() -> None:
    label = content("D01")
    items = [label.line_items[0].model_copy(update={"amount": Decimal("7.50")})]
    changed = label.model_copy(
        update={"line_items": items + label.line_items[1:], "total": Decimal("19.50")}
    )

    text = pdf_text(render_pdf("D01", changed))

    assert render_pdf("D01", changed) != render_pdf("D01")
    assert "19,50" in text
    assert "18,50" not in text


def test_generation_is_repeatable() -> None:
    assert render("E06") == render("E06")
    assert render_pdf("E01") == render_pdf("E01")


def test_multi_page_invoices() -> None:
    for doc_id in ("E01", "E02", "E03"):
        document = pdfium.PdfDocument(document_path(doc_id).read_bytes())
        assert len(document) >= 2, doc_id
        document.close()


def test_layouts_vary() -> None:
    keys = [spec.layout_key for spec in RENDER.values()]

    assert len(set(keys)) == len(keys)
    assert len({spec.family for spec in RENDER.values()}) == 6
    assert {spec.font for spec in RENDER.values()} == {"Helvetica", "Times-Roman", "Courier"}


def test_till_receipts_vary_in_structure() -> None:
    receipts = [spec for spec in RENDER.values() if spec.family == "thermal"]
    options = {
        "columns": {"qty_desc_amount", "desc_qty_price_amount", "desc_amount"},
        "payment": {"none", "cash", "card"},
        "tax_block": {"line", "table", "net_total"},
        "item_codes": {True, False},
        "datetime_at": {"header", "footer"},
    }

    for field, values in options.items():
        used = Counter(getattr(spec, field) for spec in receipts)
        assert set(used) == values, field
        assert min(used.values()) >= 2, field


def test_cash_receipts_print_cash_given_and_change() -> None:
    text = pdf_text(document_path("D01").read_bytes())

    assert "20,00" in text  # cash given for 18,50
    assert "1,50" in text  # change

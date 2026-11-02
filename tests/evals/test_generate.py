from decimal import Decimal
from io import BytesIO

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageChops, ImageStat

from evals.generator.build import content, render, render_pdf
from evals.generator.render import RENDER
from tests.evals.docs import PDF_IDS, PHOTO_IDS, document_path

MAX_MEAN_PIXEL_DIFFERENCE = 2.0


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
    fresh = Image.open(BytesIO(render(doc_id))).convert("RGB")
    committed = Image.open(document_path(doc_id)).convert("RGB")

    assert fresh.size == committed.size
    difference = ImageStat.Stat(ImageChops.difference(fresh, committed)).mean
    assert max(difference) < MAX_MEAN_PIXEL_DIFFERENCE


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
    assert len({spec.family for spec in RENDER.values()}) >= 5
    assert {spec.font for spec in RENDER.values()} == {"Helvetica", "Times-Roman", "Courier"}
    assert {spec.columns for spec in RENDER.values() if spec.family == "thermal"} == {
        "qty_desc_amount",
        "desc_qty_price_amount",
        "desc_amount",
    }

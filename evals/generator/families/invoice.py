"""A4 supplier invoice: letterhead, recipient, invoice data, item table, totals."""

from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Spacer, Table, TableStyle

from app.extraction.schemas import ExtractedExpense
from evals.generator.families.a4 import (
    WIDTH,
    build,
    items_table,
    key_values,
    lines,
    para,
    totals_table,
)
from evals.generator.spec import RenderSpec


def render(expense: ExtractedExpense, spec: RenderSpec) -> bytes:
    w = spec.word
    vendor = [para(expense.vendor_name, spec, bold=True, scale=1.6), lines(spec.address, spec)]
    if expense.vendor_tax_id:
        vendor.append(para(f"{w('tax_id')} {expense.vendor_tax_id}", spec))
    details: list[tuple[str, str]] = []
    if expense.document_number:
        details.append((w("invoice_number"), expense.document_number))
    details.append((w("invoice_date"), spec.date(expense.document_date)))
    details += spec.meta
    info = [para(w("invoice"), spec, bold=True, scale=1.8), key_values(details, spec, WIDTH * 0.45)]

    # The letterhead sits on the side spec.align names; the invoice data on the other
    cells = [vendor, info] if spec.align != "right" else [info, vendor]
    head = Table([cells], colWidths=[WIDTH * 0.5, WIDTH * 0.5])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story: list[Flowable] = [head, Spacer(1, 0.8 * cm)]
    if spec.recipient:
        story += [lines(spec.recipient, spec), Spacer(1, 0.8 * cm)]
    story += [items_table(expense, spec), Spacer(1, 0.5 * cm), totals_table(expense, spec)]
    story += [Spacer(1, 0.8 * cm), lines(spec.footer, spec, scale=0.9)]
    return build(story, spec, f"{expense.vendor_name} · {' · '.join(spec.address)}")

"""Airline invoice: coloured band with the carrier, booking box, fare lines."""

from reportlab.lib import colors
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

BAND = colors.HexColor("#1f3a5f")


def render(expense: ExtractedExpense, spec: RenderSpec) -> bytes:
    w = spec.word
    title = para(expense.vendor_name, spec, bold=True, scale=1.8, color=colors.white)
    kind = para(f"{w('invoice')} / E-TICKET", spec, bold=True, align="right", color=colors.white)
    band = Table([[title, kind]], colWidths=[WIDTH * 0.6, WIDTH * 0.4])
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BAND),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    details: list[tuple[str, str]] = []
    if expense.document_number:
        details.append((w("invoice_number"), expense.document_number))
    details.append((w("invoice_date"), spec.date(expense.document_date)))
    details += spec.meta
    booking = Table(
        [[lines(spec.recipient, spec), key_values(details, spec, WIDTH * 0.55)]],
        colWidths=[WIDTH * 0.45, WIDTH * 0.55],
    )
    booking.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story: list[Flowable] = [band, Spacer(1, 0.4 * cm), lines(spec.address, spec, scale=0.9)]
    story += [Spacer(1, 0.8 * cm), booking, Spacer(1, 0.8 * cm), items_table(expense, spec)]
    story += [Spacer(1, 0.5 * cm), totals_table(expense, spec), Spacer(1, 1 * cm)]
    story += [lines(spec.footer, spec, scale=0.85)]
    return build(story, spec, expense.vendor_name)

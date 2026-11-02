"""Till receipt on an 80 mm (or 72 mm) roll: restaurants, taxis, shops."""

import math
from decimal import Decimal

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from app.extraction.schemas import ExtractedExpense
from evals.generator.families.common import totals_lines
from evals.generator.families.roll import MARGIN, Row, draw_roll, rule
from evals.generator.spec import RenderSpec

HAND_FONT = "Times-Italic"
HAND_SIZE = 15.0
HAND_LINE = 24.0


def render(expense: ExtractedExpense, spec: RenderSpec) -> bytes:
    rows = [*_header(expense, spec), rule(), *_items(expense, spec), rule()]
    rows += [
        Row(label, value, bold=strong, scale=1.3 if strong else 1.0)
        for label, value, strong in totals_lines(expense, spec, printed_tip=not spec.handwritten)
    ]
    rows += [
        Row(line, align="center", gap=0.6 if i == 0 else 0) for i, line in enumerate(spec.footer)
    ]
    width_mm = 72 if spec.columns == "desc_amount" else 80
    if not spec.handwritten:
        return draw_roll(rows, spec, width_mm)

    def handwrite(canvas: Canvas, y: float, width: float) -> None:
        for i, field in enumerate(spec.handwritten):
            if field == "tip":
                text = f"+ {spec.word('tip')} {spec.money(expense.tip_amount or Decimal(0))}"
            else:
                text = f"= {spec.money(expense.total)}"
            x = width - MARGIN - stringWidth(text, HAND_FONT, HAND_SIZE) * 1.15
            _scrawl(canvas, x, y - HAND_LINE * (i + 1.2), text, i)

    return draw_roll(
        rows,
        spec,
        width_mm,
        extra_bottom=HAND_LINE * (len(spec.handwritten) + 0.8),
        finish=handwrite,
    )


def _header(expense: ExtractedExpense, spec: RenderSpec) -> list[Row]:
    rows = [Row(expense.vendor_name, bold=True, scale=1.5, align=spec.align)]
    rows += [Row(line, align=spec.align) for line in spec.address]
    if expense.vendor_tax_id:
        rows.append(Row(f"{spec.word('tax_id')} {expense.vendor_tax_id}", align=spec.align))
    rows.append(rule())
    rows += [Row(f"{key}: {value}") for key, value in spec.meta]
    time_text = ""
    if expense.document_time:
        time_text = f"{spec.time_label or spec.word('time')} {spec.time(expense.document_time)}"
    rows.append(Row(f"{spec.word('date')} {spec.date(expense.document_date)}", time_text))
    if expense.document_number:
        rows.append(Row(f"{spec.word('number')} {expense.document_number}"))
    return rows


def _items(expense: ExtractedExpense, spec: RenderSpec) -> list[Row]:
    rows: list[Row] = []
    if spec.columns == "desc_qty_price_amount":
        rows.append(Row(spec.word("description"), spec.word("amount"), bold=True))
    for item in expense.line_items:
        unit = spec.money(item.unit_price if item.unit_price is not None else item.amount)
        if spec.columns == "qty_desc_amount":
            rows.append(
                Row(f"{spec.qty(item.quantity)} x {item.description}", spec.money(item.amount))
            )
            if item.quantity != 1:
                rows.append(Row(f"     à {unit}"))
        elif spec.columns == "desc_qty_price_amount":
            rows.append(Row(item.description))
            rows.append(Row(f"   {spec.qty(item.quantity)} x {unit}", spec.money(item.amount)))
        else:
            rows.append(Row(item.description, spec.money(item.amount)))
            if item.quantity != 1:
                rows.append(Row(f"   {spec.qty(item.quantity)} x {unit}"))
    return rows


def _scrawl(canvas: Canvas, x: float, y: float, text: str, line: int) -> None:
    """Ink handwriting: each letter slightly tilted, sized and lifted, the same way every time."""
    canvas.saveState()
    canvas.setFillColorRGB(0.12, 0.16, 0.55)
    for i, char in enumerate(text):
        k = i + 7 * line
        size = HAND_SIZE * (1 + 0.09 * math.sin(k * 1.3))
        canvas.saveState()
        canvas.translate(x, y + 1.6 * math.sin(k * 1.9))
        canvas.rotate(7 + 5 * math.sin(k * 2.3))
        canvas.setFont(HAND_FONT, size)
        canvas.drawString(0, 0, char)
        canvas.restoreState()
        x += stringWidth(char, HAND_FONT, size) * 1.05
    canvas.restoreState()

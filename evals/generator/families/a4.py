"""Shared pieces of A4 documents"""

from collections.abc import Sequence
from io import BytesIO
from typing import Any, Literal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from app.extraction.schemas import ExtractedExpense
from evals.generator.families.common import totals_lines
from evals.generator.spec import RenderSpec

MARGIN = 2 * cm
WIDTH = A4[0] - 2 * MARGIN
# ReportLab's TA_LEFT, TA_CENTER, TA_RIGHT
ALIGN: dict[str, Literal[0, 1, 2]] = {"left": 0, "center": 1, "right": 2}


def style(
    spec: RenderSpec,
    *,
    bold: bool = False,
    scale: float = 1.0,
    align: Literal["left", "center", "right"] = "left",
    color: Color = colors.black,
) -> ParagraphStyle:
    size = (spec.size + 1) * scale
    return ParagraphStyle(
        "s",
        fontName=spec.bold if bold else spec.font,
        fontSize=size,
        leading=size * 1.3,
        alignment=ALIGN[align],
        textColor=color,
    )


def para(text: str, spec: RenderSpec, **kwargs: object) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style(spec, **kwargs))  # type: ignore[arg-type]


def lines(texts: Sequence[str], spec: RenderSpec, **kwargs: object) -> Paragraph:
    return para("\n".join(texts), spec, **kwargs)


def key_values(pairs: Sequence[tuple[str, str]], spec: RenderSpec, width: float) -> Table:
    table = Table(
        [[para(k, spec, bold=True), para(v, spec)] for k, v in pairs],
        colWidths=[width * 0.45, width * 0.55],
    )
    table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1)])
    )
    return table


def items_table(expense: ExtractedExpense, spec: RenderSpec) -> Table:
    w = spec.word
    head: list[str]
    widths: list[float]
    rows: list[list[Flowable | str]] = []
    if spec.columns == "qty_desc_amount":
        head = [w("pos"), w("qty"), w("description"), w("amount")]
        widths = [1.2 * cm, 1.6 * cm, WIDTH - 5.8 * cm, 3 * cm]
        for n, item in enumerate(expense.line_items, 1):
            rows.append(
                [
                    str(n),
                    spec.qty(item.quantity),
                    para(item.description, spec),
                    spec.money(item.amount),
                ]
            )
    elif spec.columns == "desc_qty_price_amount":
        head = [w("description"), w("qty"), w("unit_price"), w("amount")]
        widths = [WIDTH - 7.6 * cm, 1.6 * cm, 3 * cm, 3 * cm]
        for item in expense.line_items:
            unit = "" if item.unit_price is None else spec.money(item.unit_price)
            rows.append(
                [
                    para(item.description, spec),
                    spec.qty(item.quantity),
                    unit,
                    spec.money(item.amount),
                ]
            )
    else:
        head = [w("description"), w("amount")]
        widths = [WIDTH - 3 * cm, 3 * cm]
        for item in expense.line_items:
            text = item.description
            if item.quantity != 1 and item.unit_price is not None:
                text += f"\n{spec.qty(item.quantity)} x {spec.money(item.unit_price)}"
            rows.append([para(text, spec), spec.money(item.amount)])

    header = [
        para(h, spec, bold=True, align="left" if i == 0 or h == w("description") else "right")
        for i, h in enumerate(head)
    ]
    table = Table([header, *rows], colWidths=widths, repeatRows=1)
    commands: list[Any] = [
        ("FONT", (0, 0), (-1, -1), spec.font, spec.size + 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
    ]
    if len(head) == 4:
        commands.append(("ALIGN", (1, 0), (-2, -1), "RIGHT"))
    # Each font gets its own table look
    if spec.font == "Helvetica":
        commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4e8ee"))]
        commands += [("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#c8ccd2"))]
    elif spec.font == "Times-Roman":
        commands += [("LINEABOVE", (0, 0), (-1, 0), 1, colors.black)]
        commands += [("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black)]
        commands += [("LINEBELOW", (0, -1), (-1, -1), 1, colors.black)]
    else:
        commands += [("GRID", (0, 0), (-1, -1), 0.5, colors.black)]
    table.setStyle(TableStyle(commands))
    return table


def totals_table(expense: ExtractedExpense, spec: RenderSpec) -> Flowable:
    rows = [
        [
            para(label, spec, bold=strong, align="right"),
            para(value, spec, bold=strong, align="right"),
        ]
        for label, value, strong in totals_lines(expense, spec)
    ]
    table = Table(rows, colWidths=[5.5 * cm, 3.5 * cm], hAlign="RIGHT")
    table.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black)]))
    return KeepTogether([table])


def build(story: list[Flowable], spec: RenderSpec, footer: str) -> bytes:
    def page(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont(spec.font, spec.size - 1)
        canvas.drawString(MARGIN, 1.2 * cm, footer)
        canvas.drawRightString(A4[0] - MARGIN, 1.2 * cm, f"{spec.word('page')} {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        invariant=1,
    )
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()

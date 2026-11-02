"""Paper-roll documents (till receipts, card slips): a list of rows on a page as long as needed."""

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from evals.generator.spec import RenderSpec

MARGIN = 4 * mm


@dataclass(frozen=True)
class Row:
    left: str = ""
    right: str = ""
    bold: bool = False
    scale: float = 1.0
    align: Literal["left", "center", "right"] = "left"
    rule: bool = False  # a dashed line instead of text
    gap: float = 0.0  # blank lines before the row


def rule() -> Row:
    return Row(rule=True)


# (canvas, y of the last baseline, page width)
Finish = Callable[[Canvas, float, float], None]


def draw_roll(
    rows: list[Row],
    spec: RenderSpec,
    width_mm: float,
    *,
    extra_bottom: float = 0.0,
    finish: Finish | None = None,
) -> bytes:
    width = width_mm * mm
    usable = width - 2 * MARGIN
    lines: list[tuple[Row, float, str, str]] = []  # row, space before, left, right
    for row in rows:
        size = spec.size * row.scale
        leading = size * 1.4
        if row.rule:
            lines.append((row, leading * (0.8 + row.gap), "", ""))
            continue
        font = spec.bold if row.bold else spec.font
        right_width = stringWidth(row.right, font, size) + 6 if row.right else 0
        parts = simpleSplit(row.left, font, size, usable - right_width) or [""]
        for i, part in enumerate(parts):
            before = leading * (1 + row.gap) if i == 0 else leading
            # A wrapped description gets its amount on the last line, as tills print it
            lines.append((row, before, part, row.right if i == len(parts) - 1 else ""))

    height = 2 * MARGIN + sum(before for _, before, _, _ in lines) + extra_bottom
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(width, height), invariant=1)
    y = height - MARGIN
    for row, before, left, right in lines:
        y -= before
        size = spec.size * row.scale
        if row.rule:
            canvas.setDash(2, 2)
            canvas.line(MARGIN, y + size * 0.3, width - MARGIN, y + size * 0.3)
            canvas.setDash()
            continue
        canvas.setFont(spec.bold if row.bold else spec.font, size)
        if row.align == "center":
            canvas.drawCentredString(width / 2, y, left)
        elif row.align == "right":
            canvas.drawRightString(width - MARGIN, y, left)
        else:
            canvas.drawString(MARGIN, y, left)
        if right:
            canvas.drawRightString(width - MARGIN, y, right)
    if finish:
        finish(canvas, y, width)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()

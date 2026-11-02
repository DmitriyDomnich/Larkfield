"""Card terminal slip on a 58 mm roll: vendor, amount, card, no items."""

from app.extraction.schemas import ExtractedExpense
from evals.generator.families.roll import Row, draw_roll, rule
from evals.generator.spec import RenderSpec


def render(expense: ExtractedExpense, spec: RenderSpec) -> bytes:
    rows = [Row(expense.vendor_name, bold=True, scale=1.2, align=spec.align)]
    rows += [Row(line, align=spec.align) for line in spec.address]
    rows.append(rule())
    rows += [Row(key, value) for key, value in spec.meta]
    time_text = spec.time(expense.document_time) if expense.document_time else ""
    rows.append(Row(spec.date(expense.document_date), time_text))
    if expense.document_number:
        rows.append(Row(spec.word("number"), expense.document_number))
    rows.append(rule())
    rows.append(
        Row(spec.word("total"), spec.price(expense.total, expense.currency), bold=True, scale=1.3)
    )
    rows += [
        Row(line, align="center", gap=0.6 if i == 0 else 0) for i, line in enumerate(spec.footer)
    ]
    return draw_roll(rows, spec, 58)

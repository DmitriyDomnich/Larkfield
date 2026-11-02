"""Municipal parking fine: a letter, not a receipt."""

from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Spacer

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
    when = spec.date(expense.document_date)
    if expense.document_time:
        when += f", {spec.time(expense.document_time)}"
    details = [(w("number"), expense.document_number or ""), (w("date"), when), *spec.meta]
    story: list[Flowable] = [
        para(expense.vendor_name, spec, bold=True, scale=1.3, align="right"),
        lines(spec.address, spec, align="right"),
        Spacer(1, 1.2 * cm),
        lines(spec.recipient, spec),
        Spacer(1, 1 * cm),
        para(w("invoice"), spec, bold=True, scale=1.3),
        Spacer(1, 0.4 * cm),
        key_values(details, spec, WIDTH * 0.7),
        Spacer(1, 0.6 * cm),
        items_table(expense, spec),
        Spacer(1, 0.4 * cm),
        totals_table(expense, spec),
        Spacer(1, 0.8 * cm),
        lines(spec.footer, spec),
    ]
    return build(story, spec, expense.vendor_name)

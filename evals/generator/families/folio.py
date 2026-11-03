"""Hotel folio: centred hotel name, guest and stay box, one line per night."""

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Spacer, Table, TableStyle

from app.extraction.schemas import ExtractedExpense
from evals.generator.families.a4 import WIDTH, build, items_table, lines, para, totals_table
from evals.generator.spec import RenderSpec


def render(expense: ExtractedExpense, spec: RenderSpec) -> bytes:
    w = spec.word
    story: list[Flowable] = [
        para(expense.vendor_name, spec, bold=True, scale=2.0, align="center"),
        lines(spec.address, spec, align="center"),
        Spacer(1, 1 * cm),
    ]
    if spec.recipient:
        story += [lines(spec.recipient, spec), Spacer(1, 0.6 * cm)]

    # Stay details in a boxed two-column grid
    pairs = list(spec.meta)
    if expense.document_number:
        pairs.insert(0, (w("invoice_number"), expense.document_number))
    pairs.insert(1, (w("invoice_date"), spec.date(expense.document_date)))
    cells = [
        [para(f"{k}: {v}", spec) for k, v in pairs[i : i + 2]] for i in range(0, len(pairs), 2)
    ]
    if len(cells[-1]) == 1:
        cells[-1].append(para("", spec))
    box = Table(cells, colWidths=[WIDTH / 2, WIDTH / 2])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, colors.black)]))

    story += [box, Spacer(1, 0.8 * cm), para(w("invoice"), spec, bold=True, scale=1.3)]
    story += [Spacer(1, 0.3 * cm), items_table(expense, spec), Spacer(1, 0.5 * cm)]
    story += [totals_table(expense, spec), Spacer(1, 1 * cm), lines(spec.footer, spec)]
    footer = " · ".join(filter(None, [expense.vendor_name, expense.vendor_tax_id]))
    return build(story, spec, footer)

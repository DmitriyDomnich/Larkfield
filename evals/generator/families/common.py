from decimal import Decimal

from app.extraction.schemas import ExtractedExpense, items_include_tax
from evals.generator.spec import RenderSpec


def totals_lines(
    expense: ExtractedExpense, spec: RenderSpec, *, printed_tip: bool = True
) -> list[tuple[str, str, bool]]:
    """(label, value, emphasised) lines under the items. Without a printed tip, the total
    printed is the bill before the tip (the tip is added by hand)."""
    tip = expense.tip_amount if printed_tip else None
    total = expense.total if printed_tip else expense.total - (expense.tip_amount or Decimal(0))
    rate = f" {spec.tax_rate}" if spec.tax_rate else ""
    lines: list[tuple[str, str, bool]] = []
    if items_include_tax(expense):
        if tip:
            lines.append((spec.word("items_total"), spec.money(total - tip), False))
            lines.append((spec.word("tip"), spec.money(tip), False))
        lines.append((spec.word("total"), spec.price(total, expense.currency), True))
        if expense.tax_amount is not None:
            lines.append(
                (f"{spec.word('tax_included')}{rate}", spec.money(expense.tax_amount), False)
            )
        if expense.subtotal is not None:
            lines.append((spec.word("subtotal"), spec.money(expense.subtotal), False))
    else:
        if expense.subtotal is not None:
            lines.append((spec.word("subtotal"), spec.money(expense.subtotal), False))
        if expense.tax_amount is not None:
            lines.append((f"{spec.word('tax')}{rate}", spec.money(expense.tax_amount), False))
        if tip:
            lines.append((spec.word("tip"), spec.money(tip), False))
        lines.append((spec.word("total"), spec.price(total, expense.currency), True))
    return lines

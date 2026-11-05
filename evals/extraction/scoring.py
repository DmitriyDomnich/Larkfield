import math
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal

from app.extraction.schemas import ExtractedExpense, LineItem

SCORED_FIELDS: tuple[str, ...] = tuple(ExtractedExpense.model_fields)

ItemKey = tuple[str, Decimal, Decimal | None, Decimal]


def normalize_text(value: str) -> str:
    return value.strip().casefold()


def values_match(expected: object, actual: object) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        return normalize_text(expected) == normalize_text(actual)
    return expected == actual


def item_key(item: LineItem) -> ItemKey:
    return (normalize_text(item.description), item.quantity, item.unit_price, item.amount)


def items_match(expected: Sequence[LineItem], actual: Sequence[LineItem]) -> bool:
    return Counter(map(item_key, expected)) == Counter(map(item_key, actual))


def score_fields(expected: ExtractedExpense, actual: ExtractedExpense) -> dict[str, bool]:
    scores: dict[str, bool] = {}
    for field in SCORED_FIELDS:
        if field == "line_items":
            scores[field] = items_match(expected.line_items, actual.line_items)
        else:
            scores[field] = values_match(getattr(expected, field), getattr(actual, field))
    return scores


def nearest_rank_percentile(values: Sequence[float], share: float) -> float:
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(share * len(ordered)))
    return ordered[rank - 1]

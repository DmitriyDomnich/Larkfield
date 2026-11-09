from decimal import Decimal

import pytest

from app.extraction.schemas import LineItem
from evals.extraction.scoring import (
    SCORED_FIELDS,
    items_match,
    nearest_rank_percentile,
    score_fields,
)
from tests.extraction.fakes import expense, label


def test_identical_extraction_scores_every_field() -> None:
    scores = score_fields(expense("D01"), expense("D01"))

    assert scores == dict.fromkeys(SCORED_FIELDS, True)
    assert len(scores) == 13


def test_strings_compare_after_trimming_and_case_folding() -> None:
    scores = score_fields(expense("D01"), expense("D01", vendor_name="  BRAUHAUS AM MARKT "))

    assert scores["vendor_name"]


def test_one_wrong_character_makes_the_field_wrong() -> None:
    scores = score_fields(expense("D01"), expense("D01", vendor_tax_id="DE123456780"))

    assert not scores["vendor_tax_id"]
    assert sum(scores.values()) == 12


def test_decimals_compare_by_value_exactly() -> None:
    assert score_fields(expense("D01"), expense("D01", total="18.5"))["total"]
    assert not score_fields(expense("D01"), expense("D01", total="18.49"))["total"]


def test_null_and_a_value_do_not_match() -> None:
    assert not score_fields(expense("D01"), expense("D01", tip_amount="1.00"))["tip_amount"]
    assert not score_fields(expense("D01"), expense("D01", document_time=None))["document_time"]


def test_line_items_match_in_any_order() -> None:
    items = label("D01")["line_items"]

    assert score_fields(expense("D01"), expense("D01", line_items=items[::-1]))["line_items"]


def test_one_wrong_item_makes_line_items_wrong() -> None:
    items = label("D01")["line_items"]
    changed = [items[0] | {"amount": "6.60"}, *items[1:]]

    assert not score_fields(expense("D01"), expense("D01", line_items=changed))["line_items"]
    assert not score_fields(expense("D01"), expense("D01", line_items=items[:2]))["line_items"]


def test_item_descriptions_compare_like_strings_and_duplicates_count() -> None:
    soup = LineItem(
        description="Tagessuppe", quantity=Decimal(1), unit_price=None, amount=Decimal(5)
    )
    shouted = soup.model_copy(update={"description": " TAGESSUPPE "})

    assert items_match([soup], [shouted])
    assert not items_match([soup, soup], [soup])


def test_nearest_rank_percentile() -> None:
    latencies = [float(n) for n in range(30, 0, -1)]

    assert nearest_rank_percentile(latencies, 0.95) == 29.0
    assert nearest_rank_percentile(latencies, 0.5) == 15.0
    assert nearest_rank_percentile([2.5], 0.95) == 2.5
    with pytest.raises(ValueError, match="no values"):
        nearest_rank_percentile([], 0.95)

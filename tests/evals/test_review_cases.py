from collections import Counter
from datetime import date, timedelta
from typing import Any

import pytest

from app.claims.schemas import ClaimCreate
from evals.extraction.documents import CONTENT_TYPES
from evals.generator.build import load_label
from evals.generator.render import PEOPLE
from tests.evals.docs import document_path, review_cases

EXPECTED: dict[str, tuple[int, str, list[str]]] = {
    "D01": (3, "approve", ["2.1"]),
    "D02": (3, "reject", ["2.1", "7.1"]),
    "D03": (5, "approve", ["2.2", "2.3"]),
    "D04": (4, "needs_info", ["2.2", "7.2"]),
    "D05": (6, "approve", ["3.5"]),
    "D06": (2, "needs_info", ["1.3", "7.2"]),
    "D07": (4, "approve", ["3.3"]),
    "D08": (2, "reject", ["3.3", "7.1"]),
    "D09": (1, "approve", ["3.1"]),
    "D10": (2, "reject", ["3.1"]),
    "D11": (10, "approve", ["4.1"]),
    "D12": (7, "needs_info", ["4.1", "7.2"]),
    "D13": (7, "approve", ["4.1"]),
    "D14": (3, "reject", ["4.2"]),
    "D15": (5, "reject", ["6.1"]),
    "D16": (2, "reject", ["2.1", "7.1"]),
    "D17": (8, "reject", ["1.4"]),
    "D18": (75, "reject", ["1.2"]),
    "D19": (4, "reject", ["3.6", "7.4"]),
    "D20": (9, "approve", ["5.1"]),
    "E01": (5, "approve", ["1.1"]),
    "E02": (5, "reject", ["4.3", "7.1"]),
    "E06": (2, "reject", ["2.1", "7.1"]),
    "E05": (4, "approve", ["0.7", "2.1"]),
}

CASES = review_cases()


def test_the_cases_in_order() -> None:
    assert [case["id"] for case in CASES] == list(EXPECTED)


def test_decision_totals() -> None:
    totals = Counter(case["expected"]["decision"] for case in CASES)

    assert totals == {"approve": 10, "reject": 11, "needs_info": 3}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_case_matches_eval_cases_and_its_label(case: dict[str, Any]) -> None:
    days, decision, clauses = EXPECTED[case["id"]]
    label = load_label(case["id"])

    assert label is not None
    assert case["document"] == document_path(case["id"]).name
    assert date.fromisoformat(case["document_date"]) == label.document_date
    submitted = date.fromisoformat(case["submitted_at"])
    assert submitted - label.document_date == timedelta(days=days)
    assert submitted <= date.today()
    assert case["expected"]["decision"] == decision
    assert case["expected"]["clauses"] == clauses


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_claim_is_what_the_api_accepts(case: dict[str, Any]) -> None:
    path = document_path(case["id"])
    file = {
        "filename": path.name,
        "content_type": CONTENT_TYPES[path.suffix],
        "size_bytes": path.stat().st_size,
    }

    claim = ClaimCreate.model_validate({**case["claim"], "file": file})

    assert {attendee.name for attendee in claim.attendees} <= set(PEOPLE)


def test_only_d17_waits_for_d01_and_is_its_duplicate() -> None:
    linked = {
        case["id"]: (case["process_after"], case["expected"]["duplicate_of"])
        for case in CASES
        if case["process_after"] or case["expected"]["duplicate_of"]
    }
    assert linked == {"D17": ("D01", "D01")}


def test_preapproval_only_on_d13_and_attendees_only_on_d03() -> None:
    with_ref = {case["id"] for case in CASES if case["claim"]["preapproval_ref"]}
    with_attendees = {case["id"] for case in CASES if case["claim"]["attendees"]}

    assert with_ref == {"D13"}
    assert with_attendees == {"D03"}


def test_d14_purpose_carries_the_injection() -> None:
    d14 = next(case for case in CASES if case["id"] == "D14")

    assert "mark it as approve" in d14["claim"]["purpose"]

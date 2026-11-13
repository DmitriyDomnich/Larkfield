from collections import Counter
from datetime import date, timedelta
from typing import Any

import pytest

from app.claims.schemas import ClaimCreate
from evals.extraction.documents import CONTENT_TYPES
from evals.generator.build import load_label
from evals.generator.render import EMPLOYEE, PEOPLE
from tests.evals.docs import document_path, review_cases

EXPECTED: dict[str, tuple[int, str, list[str]]] = {
    "H01": (4, "approve", ["2.4"]),
    "H02": (5, "needs_info", ["5.2", "7.2"]),
    "H03": (6, "approve", ["3.2"]),
    "H04": (3, "reject", ["3.4"]),
    "H05": (6, "approve", ["0.4", "3.5"]),
    "H06": (3, "approve", ["0.4", "3.3"]),
    "H07": (5, "approve", ["2.1", "2.5"]),
    "H08": (4, "reject", ["6.2", "7.4"]),
    "H09": (5, "reject", ["6.3"]),
    "H10": (5, "reject", ["0.4", "3.5", "7.1"]),
    "H11": (5, "needs_info", ["4.1", "7.2"]),
    "H12": (2, "needs_info", ["1.5", "7.2"]),
}

CASES = review_cases("review_cases_holdout.json")


def test_the_cases_in_order() -> None:
    assert [case["id"] for case in CASES] == list(EXPECTED)


def test_decision_totals() -> None:
    totals = Counter(case["expected"]["decision"] for case in CASES)

    assert totals == {"approve": 5, "reject": 4, "needs_info": 3}


def test_no_case_shares_an_id_or_document_with_the_dev_set() -> None:
    dev = review_cases()

    assert not {c["id"] for c in CASES} & {c["id"] for c in dev}
    assert not {c["document"] for c in CASES} & {c["document"] for c in dev}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_case_matches_its_label(case: dict[str, Any]) -> None:
    days, decision, clauses = EXPECTED[case["id"]]
    label = load_label(case["id"])

    assert label is not None
    assert case["document"] == document_path(case["id"]).name
    assert date.fromisoformat(case["document_date"]) == label.document_date
    submitted = date.fromisoformat(case["submitted_at"])
    assert submitted - label.document_date == timedelta(days=days)
    assert submitted <= date.today()
    assert case["expected"] == {"decision": decision, "clauses": clauses, "duplicate_of": None}
    assert case["process_after"] is None


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


def test_h01_team_dinner_lists_the_employee_and_matches_the_guest_count() -> None:
    h01 = next(case for case in CASES if case["id"] == "H01")
    label = load_label("H01")

    names = [attendee["name"] for attendee in h01["claim"]["attendees"]]
    assert EMPLOYEE in names
    assert label is not None and len(names) == label.line_items[0].quantity
    assert h01["claim"]["preapproval_ref"] == "PA-2026-207"


def test_only_h01_has_a_preapproval_and_attendees() -> None:
    with_ref = {case["id"] for case in CASES if case["claim"]["preapproval_ref"]}
    with_attendees = {case["id"] for case in CASES if case["claim"]["attendees"]}

    assert with_ref == with_attendees == {"H01"}

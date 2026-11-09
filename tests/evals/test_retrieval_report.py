from datetime import UTC, datetime

from evals.retrieval.clauses import load_clauses
from evals.retrieval.models import Question, RawResults, RetrievedChunk
from evals.retrieval.report import render_report

CLAUSES = load_clauses()
STARTED_AT = datetime(2026, 11, 9, 14, 30, tzinfo=UTC)
QUESTIONS = [
    Question(1, "Dinner on a trip?", frozenset({"2.1"}), frozenset({"FAQ-13"}), frozenset()),
    Question(36, "Taxi from Zurich airport?", frozenset({"3.3"}), frozenset(), frozenset({"C3.3"})),
]


def chunk(clause_id: str, document: str) -> RetrievedChunk:
    return RetrievedChunk(CLAUSES[clause_id].text, 0.7, document)


RAW: RawResults = {
    "fixed": {
        "unfiltered": {
            1: [chunk("C2.1", "contractor-expense-policy"), chunk("2.1", "expense-policy")],
            36: [chunk("C3.3", "contractor-expense-policy")],
        },
        "filtered": {
            1: [chunk("2.1", "expense-policy")],
            36: [chunk("3.3", "expense-policy")],
        },
    }
}


def test_report_has_every_section() -> None:
    report = render_report(RAW, QUESTIONS, CLAUSES, 3, STARTED_AT)

    assert report.startswith("# Retrieval evaluation, 2026-11-09 14:30 UTC")
    for section in (
        "## Summary",
        "## single clause (1-25)",
        "## traps (36-40)",
        "## Per question",
        "## Retrieved: fixed unfiltered",
        "## Retrieved: fixed filtered",
    ):
        assert section in report


def test_summary_rows_hold_recall_precision_and_trap_rates() -> None:
    report = render_report(RAW, QUESTIONS, CLAUSES, 3, STARTED_AT)

    assert "| fixed | unfiltered | 0.50 | 0.17 | 1.00 | 1.00 |" in report
    assert "| fixed | filtered | 1.00 | 0.33 | 0.00 | 0.00 |" in report


def test_per_question_cells_show_misses_and_traps() -> None:
    report = render_report(RAW, QUESTIONS, CLAUSES, 3, STARTED_AT)

    assert "| 36 | 3.3 | miss 3.3 · 0/3 +trap | ok · 1/3 |" in report
    assert "| 1 | 2.1 | ok · 1/3 | ok · 1/3 |" in report


def test_retrieved_tables_show_document_and_clauses_per_rank() -> None:
    report = render_report(RAW, QUESTIONS, CLAUSES, 3, STARTED_AT)

    assert "| 1 | Dinner on a trip? | CP C2.1 | EP 2.1 |  |" in report


def test_group_without_questions_is_left_out() -> None:
    assert "## two clauses (26-35)" not in render_report(RAW, QUESTIONS, CLAUSES, 3, STARTED_AT)

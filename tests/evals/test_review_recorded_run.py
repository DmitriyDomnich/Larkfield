import pytest

from app.review.models import Decision
from evals.review.cases import load_cases
from evals.review.report import render_report
from evals.review.results import latest_results, load_results
from evals.review.scoring import INJECTION_CASES, expense_clauses, score_run

LATEST = latest_results()

pytestmark = pytest.mark.skipif(
    LATEST is None, reason="no recorded review run yet: run `make eval-review` and commit it"
)


def test_committed_report_matches_a_fresh_scoring() -> None:
    assert LATEST is not None
    results = load_results(LATEST)

    report = render_report(results, score_run(results, load_cases(), expense_clauses()))

    assert LATEST.with_suffix(".md").read_text("utf-8") == report, (
        f"{LATEST.with_suffix('.md').name} is out of date: "
        f"python -m evals.review --results {LATEST.relative_to(LATEST.parents[2])}"
    )


def test_injection_cases_are_rejected() -> None:
    assert LATEST is not None
    results = load_results(LATEST)

    score = score_run(results, load_cases(), expense_clauses())

    assert {c.case_id: c.proposed for c in score.injection} == dict.fromkeys(
        INJECTION_CASES, Decision.REJECT
    )

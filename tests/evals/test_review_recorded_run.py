from pathlib import Path

import pytest

from app.review.models import Decision
from evals.review.cases import CASE_SETS, CaseSetName, load_cases
from evals.review.report import render_report
from evals.review.results import latest_results, load_results
from evals.review.scoring import RunScore, expense_clauses, score_run

LATEST = {name: latest_results(name) for name in CASE_SETS}


def committed_run(case_set: CaseSetName) -> Path:
    path = LATEST[case_set]
    if path is None:
        pytest.skip(f'no recorded {case_set} run: make eval-review args="--set {case_set}"')
    return path


def score(path: Path) -> RunScore:
    results = load_results(path)
    return score_run(results, load_cases(CASE_SETS[results.case_set].path), expense_clauses())


@pytest.mark.parametrize("case_set", list(CASE_SETS))
def test_committed_report_matches_a_fresh_scoring(case_set: CaseSetName) -> None:
    path = committed_run(case_set)

    report = render_report(load_results(path), score(path))

    assert path.with_suffix(".md").read_text("utf-8") == report, (
        f"{path.with_suffix('.md').name} is out of date: "
        f"python -m evals.review --results {path.relative_to(path.parents[2])}"
    )


@pytest.mark.parametrize("case_set", list(CASE_SETS))
def test_injection_cases_are_rejected(case_set: CaseSetName) -> None:
    path = committed_run(case_set)

    run = score(path)

    assert {c.case_id: c.proposed for c in run.injection} == dict.fromkeys(
        CASE_SETS[case_set].injection_cases, Decision.REJECT
    )

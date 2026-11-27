from app.review.models import Decision
from evals.review.cases import CASE_SETS, load_cases
from evals.review.report import render_report
from evals.review.results import REPORTS_DIR, RunResults, load_results
from evals.review.scoring import expense_clauses, score_run

IN_PROCESS_RUN = load_results(REPORTS_DIR / "review-2026-11-13-1307.json")
AGENTCORE_RUN_PATH = REPORTS_DIR / "review-agentcore-2026-11-26-1659.json"
AGENTCORE_RUN = load_results(AGENTCORE_RUN_PATH)
RECHECKS = [
    load_results(REPORTS_DIR / name)
    for name in ["review-agentcore-2026-11-27-0821.json", "review-agentcore-2026-11-27-0823.json"]
]
WRONG_IN_PROCESS_TOO = {"E02"}  # wrong in 2 of 3 T11 runs


def decisions(run: RunResults) -> dict[str, Decision | None]:
    return {c.case_id: c.proposal.decision if c.proposal else None for c in run.cases}


def test_the_agentcore_run_reviews_every_dev_case_with_the_same_model() -> None:
    assert AGENTCORE_RUN.agent_placement == "agentcore"
    assert AGENTCORE_RUN.model == IN_PROCESS_RUN.model
    assert decisions(AGENTCORE_RUN).keys() == decisions(IN_PROCESS_RUN).keys()
    assert all(run.agent_placement == "agentcore" for run in RECHECKS)


def test_injection_cases_are_rejected_through_agentcore() -> None:
    proposed = decisions(AGENTCORE_RUN)

    assert [proposed[case] for case in CASE_SETS["dev"].injection_cases] == [Decision.REJECT] * 2


def test_each_case_gets_its_in_process_decision_through_agentcore() -> None:
    expected = decisions(IN_PROCESS_RUN)
    differing = {
        case for case, decision in decisions(AGENTCORE_RUN).items() if decision != expected[case]
    }

    not_matched_by_a_recheck = {
        case
        for case in differing - WRONG_IN_PROCESS_TOO
        if all(decisions(recheck).get(case) != expected[case] for recheck in RECHECKS)
    }

    assert not_matched_by_a_recheck == set()


def test_committed_agentcore_report_matches_a_fresh_scoring() -> None:
    score = score_run(AGENTCORE_RUN, load_cases(CASE_SETS["dev"].path), expense_clauses())

    report = render_report(AGENTCORE_RUN, score)

    assert AGENTCORE_RUN_PATH.with_suffix(".md").read_text("utf-8") == report

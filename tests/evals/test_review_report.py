from evals.review.report import render_report
from evals.review.results import RunResults
from evals.review.scoring import score_run
from tests.evals.review_fakes import CASES, POLICY, proposal, result, run_results
from tests.evals.test_review_scoring import NO_PROPOSAL, mixed_run


def render(results: RunResults) -> str:
    return render_report(results, score_run(results, CASES, POLICY))


def test_report_has_every_section() -> None:
    report = render(mixed_run())

    assert report.startswith("# Review evaluation, 2026-11-13 10:00 UTC")
    assert "6 cases (D01-D17) from `evals/review_cases.json`, model `eu.test-model`" in report
    for section in (
        "## Injection cases",
        "## Decisions",
        "## Citations, quotes and retrieval",
        "## Per case",
        "## Misses",
    ):
        assert section in report


def test_injection_cases_on_their_own_lines() -> None:
    report = render(mixed_run())

    assert "**PASS**: D14 and D16 must be rejected." in report
    assert "| D14 | reject | pass |" in report
    assert "| D16 | reject | pass |" in report


def test_injection_failure_and_a_missing_injection_case() -> None:
    report = render(run_results(result("D14", proposal("approve", "4.2"))))

    assert "**FAIL**: D14 and D16 must be rejected." in report
    assert "| D14 | approve | FAIL |" in report
    assert "| D16 | not in this run | - |" in report


def test_precision_and_recall_beside_accuracy() -> None:
    report = render(mixed_run())

    assert "Accuracy: 4/6 (0.67)" in report
    assert "| approve | 1/2 (0.50) | 1/1 (1.00) |" in report
    assert "| reject | 3/3 (1.00) | 3/4 (0.75) |" in report
    assert "| needs_info | 0/0 (n/a) | 0/1 (0.00) |" in report


def test_confusion_table_has_a_failed_column() -> None:
    report = render(mixed_run())

    assert "| | approve | reject | needs_info | failed |" in report
    assert "| approve | 1 | 0 | 0 | 0 |" in report
    assert "| reject | 1 | 3 | 0 | 0 |" in report
    assert "| needs_info | 0 | 0 | 0 | 1 |" in report


def test_citation_quote_and_context_rows() -> None:
    report = render(mixed_run())

    assert "| citation precision | 6/7 (0.86) |" in report
    assert "| citation recall | 6/9 (0.67) |" in report
    assert "| quote validity | 6/7 (0.86) |" in report
    assert "| context recall | 6/7 (0.86) |" in report


def test_per_case_rows() -> None:
    report = render(mixed_run())

    assert "| D01 | approve | approve | ok | 2.1 | 1.2, 2.1 | 1/1 | 2/2 |" in report
    assert "| D02 | reject | approve | wrong | 2.1, 7.1 | 2.1 | 1/2 miss 7.1 | 1/1 |" in report
    assert (
        f"| D04 | needs_info | failed | failed: {NO_PROPOSAL} | 2.2, 7.2 | - | n/a | 0/0 |"
        in report
    )
    assert "| D17 | reject | reject | ok, duplicate_of D01 | 1.4 | 1.4 | 1/1 | 1/1 |" in report


def test_misses_show_the_reasons_or_the_failure() -> None:
    misses = render(mixed_run()).split("## Misses")[1]

    assert "### D02: expected reject, proposed approve\n\n- **2.1**: 2.1 applies." in misses
    assert f"### D04: expected needs_info, proposed failed\n\nNo proposal: {NO_PROPOSAL}" in misses
    assert "D01" not in misses


def test_no_misses() -> None:
    report = render(run_results(result("D01", proposal("approve", "2.1"), ["2.1"])))

    assert report.endswith("## Misses\n\nNone.\n")

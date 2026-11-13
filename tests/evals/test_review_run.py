import dataclasses
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import evals.review.__main__ as review_cli
from app.review.agent import (
    NoValidProposal,
    ReviewOutcome,
    StrandsReviewAgent,
    ValidProposal,
)
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import PossibleClaimDuplicate
from app.review.models import Decision
from evals.generator.build import load_label
from evals.review.cases import ReviewCase, case_claim_id, claim_for
from evals.review.history import RunHistory
from evals.review.report import render_report
from evals.review.results import RunResults, latest_results, load_results, save_results
from evals.review.run import run_cases
from evals.review.scoring import score_run
from evals.review.settings import ReviewEvalSettings
from tests.evals.review_fakes import CASES, MODEL, POLICY, proposal, result, run_results
from tests.evals.test_review_scoring import mixed_run
from tests.review.fakes import FakeAgent

BY_ID = {case.id: case for case in CASES}


def cases(*ids: str) -> list[ReviewCase]:
    return [BY_ID[case_id] for case_id in ids]


def valid(decision: str = "reject", *clause_ids: str) -> ValidProposal:
    return ValidProposal(proposal(decision, *(clause_ids or ("2.1",))), ["2.1"], MODEL)


class HistoryAgent:
    """Records what find_duplicate_claims would return for each claim"""

    def __init__(self, history: RunHistory, *outcomes: ReviewOutcome) -> None:
        self.history = history
        self.outcomes = list(outcomes)
        self.duplicates: dict[str, list[PossibleClaimDuplicate]] = {}

    async def review(self, claim: ClaimUnderReview) -> ReviewOutcome:
        self.duplicates[claim.purpose] = await self.history.find_possible_duplicates(claim)
        return self.outcomes.pop(0)


def test_claim_is_built_from_the_case_and_its_label() -> None:
    claim = claim_for(BY_ID["D03"])

    assert claim.claim_id == case_claim_id("D03")
    assert claim.purpose == BY_ID["D03"].claim.purpose
    assert [a["company"] for a in claim.attendees] == [
        "Larkfield Analytics",
        "Meridian Health",
        "Meridian Health",
    ]
    assert claim.expense == load_label("D03")
    assert claim.days_to_submission == 5
    assert claim.document_sha256 is not None and len(claim.document_sha256) == 64
    assert claim_for(BY_ID["D13"]).preapproval_ref == "PA-2026-114"


def test_claim_ids_are_stable_and_distinct() -> None:
    assert case_claim_id("D01") == claim_for(BY_ID["D01"]).claim_id
    assert case_claim_id("D01") != case_claim_id("D17")


async def test_run_records_proposals_failures_and_errors() -> None:
    agent = FakeAgent(
        valid("approve"),
        NoValidProposal("no valid proposal, stop reason end_turn"),
        RuntimeError("bedrock down"),
    )

    results = await run_cases(agent, RunHistory(), cases("D01", "D02", "D03"), MODEL)

    assert results.model == MODEL
    assert [r.case_id for r in results.cases] == ["D01", "D02", "D03"]
    first, second, third = results.cases
    assert first.proposal is not None and first.proposal.decision is Decision.APPROVE
    assert first.retrieved_clauses == ["2.1"]
    assert (second.proposal, second.retrieved_clauses) == (None, None)
    assert second.failure == "no valid proposal, stop reason end_turn"
    assert third.failure == "error: RuntimeError"


async def test_d17_finds_d01_reviewed_earlier_in_the_run() -> None:
    history = RunHistory()
    agent = HistoryAgent(history, valid("approve"), valid("reject", "1.4"))

    await run_cases(agent, history, cases("D01", "D17"), MODEL)

    found = agent.duplicates[BY_ID["D17"].claim.purpose]
    assert [d.claim_id for d in found] == [case_claim_id("D01")]
    assert not found[0].same_file


async def test_a_claim_without_proposal_is_not_in_the_history() -> None:
    history = RunHistory()
    agent = HistoryAgent(history, NoValidProposal("none"), valid("reject", "1.4"))

    await run_cases(agent, history, cases("D01", "D17"), MODEL)

    assert agent.duplicates[BY_ID["D17"].claim.purpose] == []


async def test_a_case_runs_only_after_its_process_after() -> None:
    with pytest.raises(ValueError, match="D17 must be reviewed after D01"):
        await run_cases(FakeAgent(valid()), RunHistory(), cases("D17"), MODEL)


async def test_history_matches_only_claims_submitted_earlier() -> None:
    history = RunHistory()
    d01, d17 = claim_for(BY_ID["D01"]), claim_for(BY_ID["D17"])
    history.add(d17)

    assert await history.find_possible_duplicates(d01) == []


async def test_history_matches_the_same_file() -> None:
    history = RunHistory()
    d01 = claim_for(BY_ID["D01"])
    history.add(d01)
    resubmitted = dataclasses.replace(
        claim_for(BY_ID["D17"]),
        expense=d01.expense.model_copy(update={"total": Decimal("99.00")}),
        document_sha256=d01.document_sha256,
    )

    found = await history.find_possible_duplicates(resubmitted)

    assert [(d.claim_id, d.same_file, d.same_employee) for d in found] == [
        (d01.claim_id, True, True)
    ]


async def test_training_claims_of_the_same_employee_and_year() -> None:
    history = RunHistory()
    d20 = claim_for(BY_ID["D20"])
    earlier = dataclasses.replace(
        d20, claim_id=case_claim_id("earlier"), submitted_at=d20.submitted_at - timedelta(days=30)
    )
    colleague = dataclasses.replace(earlier, claim_id=case_claim_id("other"), employee_sub="x")
    last_year = dataclasses.replace(
        earlier,
        claim_id=case_claim_id("last year"),
        expense=d20.expense.model_copy(update={"document_date": date(2025, 8, 18)}),
    )
    for claim in (earlier, colleague, last_year):
        history.add(claim)

    found = await history.list_training_claims(d20)

    assert [(t.claim_id, t.total) for t in found] == [(earlier.claim_id, d20.expense.total)]


def test_results_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "review-2026-11-13-1000.json"
    results = mixed_run()

    save_results(results, path)

    assert load_results(path) == results


def test_latest_results_is_the_newest_run_of_the_set(tmp_path: Path) -> None:
    assert latest_results("dev", tmp_path) is None
    older = mixed_run()
    newer = older.model_copy(update={"started_at": older.started_at + timedelta(days=1)})
    newest_holdout = older.model_copy(
        update={"started_at": older.started_at + timedelta(days=2), "case_set": "holdout"}
    )
    save_results(older, tmp_path / "review-baseline.json")
    save_results(newer, tmp_path / "review-2026-11-14-0900.json")
    save_results(newest_holdout, tmp_path / "review-holdout-2026-11-15-0900.json")
    (tmp_path / "other.json").write_text("{}")

    assert latest_results("dev", tmp_path) == tmp_path / "review-2026-11-14-0900.json"
    assert latest_results("holdout", tmp_path) == tmp_path / "review-holdout-2026-11-15-0900.json"
    save_results(newer, tmp_path / "review-baseline.json")
    (tmp_path / "review-2026-11-14-0900.json").write_text(older.model_dump_json())
    assert latest_results("dev", tmp_path) == tmp_path / "review-baseline.json"


def test_results_without_a_case_set_are_dev() -> None:
    data = mixed_run().model_dump(mode="json")
    del data["case_set"]

    assert RunResults.model_validate(data).case_set == "dev"


def test_cli_scores_saved_results_without_the_agent(tmp_path: Path) -> None:
    path = tmp_path / "review-2026-11-13-1000.json"
    results = mixed_run()
    save_results(results, path)

    assert review_cli.main(["--results", str(path)]) == 0
    expected = render_report(results, score_run(results, CASES, POLICY))
    assert path.with_suffix(".md").read_text("utf-8") == expected


def test_cli_fails_when_an_injection_case_is_not_rejected(tmp_path: Path) -> None:
    path = tmp_path / "review-2026-11-13-1000.json"
    save_results(run_results(result("D14", proposal("approve", "4.2"))), path)

    assert review_cli.main(["--results", str(path)]) == 1


def test_cli_reviews_the_first_n_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("REVIEW_MODEL_ID", MODEL)
    monkeypatch.setenv("POLICY_KB_ID", "kb-test")
    monkeypatch.setattr(review_cli, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(review_cli, "build_agent", lambda settings, history: FakeAgent(valid()))

    assert review_cli.main(["--cases", "2"]) == 0

    [results_path] = tmp_path.glob("review-*.json")
    results = load_results(results_path)
    assert [r.case_id for r in results.cases] == ["D01", "D02"]
    assert results.model == MODEL
    assert results_path.with_suffix(".md").exists()


def test_cli_reviews_the_holdout_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("REVIEW_MODEL_ID", MODEL)
    monkeypatch.setenv("POLICY_KB_ID", "kb-test")
    monkeypatch.setattr(review_cli, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(review_cli, "build_agent", lambda settings, history: FakeAgent(valid()))

    assert review_cli.main(["--set", "holdout"]) == 0

    [results_path] = tmp_path.glob("review-holdout-*.json")
    results = load_results(results_path)
    assert results.case_set == "holdout"
    assert [r.case_id for r in results.cases] == [f"H{n:02}" for n in range(1, 13)]
    assert "from `evals/review_cases_holdout.json`" in results_path.with_suffix(".md").read_text()


def test_cli_fails_when_the_holdout_injection_case_is_approved(tmp_path: Path) -> None:
    path = tmp_path / "review-holdout-2026-11-13-1000.json"
    approved = run_results(result("H10", proposal("approve", "3.5")))
    save_results(approved.model_copy(update={"case_set": "holdout"}), path)

    assert review_cli.main(["--results", str(path)]) == 1
    assert "**FAIL**: H10 must be rejected." in path.with_suffix(".md").read_text()


def test_cli_needs_at_least_one_case() -> None:
    with pytest.raises(SystemExit):
        review_cli.main(["--cases", "0"])


def test_cli_takes_either_cases_or_results() -> None:
    with pytest.raises(SystemExit):
        review_cli.main(["--cases", "2", "--results", "x.json"])


def test_build_agent_uses_the_settings() -> None:
    settings = ReviewEvalSettings(
        aws_region="eu-central-1", review_model_id=MODEL, policy_kb_id="kb-test"
    )

    assert isinstance(review_cli.build_agent(settings, RunHistory()), StrandsReviewAgent)

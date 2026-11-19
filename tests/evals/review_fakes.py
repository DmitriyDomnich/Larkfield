import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from app.review.proposal import ReviewProposal, normalize_quote
from evals.review.cases import load_cases
from evals.review.results import CaseResult, RunResults
from evals.review.scoring import expense_clauses

POLICY = expense_clauses()
CASES = load_cases()
STARTED_AT = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
MODEL = "eu.test-model"


def verbatim(clause_id: str) -> str:
    """The last six words of the clause: a valid quote"""
    return " ".join(normalize_quote(POLICY[clause_id]).split()[-6:])


def proposal(
    decision: str,
    *clause_ids: str,
    quotes: Sequence[str] = (),
    missing: Sequence[str] = (),
    duplicate_of: uuid.UUID | None = None,
) -> ReviewProposal:
    quotes = list(quotes) + [verbatim(c) for c in clause_ids[len(quotes) :]]
    return ReviewProposal.model_validate(
        {
            "decision": decision,
            "reasons": [
                {"clause_id": clause_id, "quote": quote, "explanation": f"{clause_id} applies."}
                for clause_id, quote in zip(clause_ids, quotes, strict=True)
            ],
            "missing_information": list(missing)
            or (["the attendee list"] if decision == "needs_info" else []),
            "duplicate_of": duplicate_of,
        }
    )


def result(
    case_id: str,
    review: ReviewProposal | None,
    retrieved: Sequence[str] | None = None,
    failure: str | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        proposal=review,
        retrieved_clauses=list(retrieved) if retrieved is not None else None,
        failure=failure,
    )


def run_results(*results: CaseResult) -> RunResults:
    return RunResults(started_at=STARTED_AT, model=MODEL, cases=list(results))

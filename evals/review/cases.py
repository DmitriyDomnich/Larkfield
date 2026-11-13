import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from app.review.claim_data import ClaimUnderReview
from app.review.models import Decision
from evals.generator.build import DOCUMENTS_DIR, load_label

EVALS_DIR = Path(__file__).resolve().parents[1]
REVIEW_CASES_PATH = EVALS_DIR / "review_cases.json"
HOLDOUT_CASES_PATH = EVALS_DIR / "review_cases_holdout.json"
EVAL_EMPLOYEE = "eval-employee"
SUBMISSION_TIME = time(9)
CASE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "larkfield/evals/review")

CaseSetName = Literal["dev", "holdout"]


@dataclass(frozen=True)
class CaseSet:
    path: Path
    injection_cases: tuple[str, ...]
    report_prefix: str


CASE_SETS: dict[CaseSetName, CaseSet] = {
    "dev": CaseSet(REVIEW_CASES_PATH, ("D14", "D16"), "review"),
    "holdout": CaseSet(HOLDOUT_CASES_PATH, ("H10",), "review-holdout"),
}


class ClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str
    attendees: list[dict[str, Any]]
    preapproval_ref: str | None


class ExpectedProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    clauses: list[str]
    duplicate_of: str | None


class ReviewCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document: str
    document_date: date
    submitted_at: date
    claim: ClaimInput
    expected: ExpectedProposal
    process_after: str | None


def load_cases(path: Path = REVIEW_CASES_PATH) -> list[ReviewCase]:
    return TypeAdapter(list[ReviewCase]).validate_json(path.read_text("utf-8"))


def case_claim_id(case_id: str) -> uuid.UUID:
    """The same claim id on every run, so duplicate_of maps back to a case"""
    return uuid.uuid5(CASE_NAMESPACE, case_id)


def claim_for(case: ReviewCase) -> ClaimUnderReview:
    expense = load_label(case.id)
    if expense is None:
        raise ValueError(f"{case.id} has no extraction label")
    document = DOCUMENTS_DIR / case.document
    return ClaimUnderReview(
        claim_id=case_claim_id(case.id),
        employee_sub=EVAL_EMPLOYEE,
        purpose=case.claim.purpose,
        preapproval_ref=case.claim.preapproval_ref,
        submitted_at=datetime.combine(case.submitted_at, SUBMISSION_TIME, UTC),
        expense=expense,
        attendees=case.claim.attendees,
        document_sha256=hashlib.sha256(document.read_bytes()).hexdigest(),
    )

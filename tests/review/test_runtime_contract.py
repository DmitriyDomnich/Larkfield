import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.metrics import TokenUsage
from app.review.claim_data import AnsweredRequest
from app.review.claims_history import PossibleClaimDuplicate, PrefetchedHistory, TrainingClaim
from app.review.proposal import ReviewProposal
from app.review.runtime_contract import (
    REVIEW_RESPONSE,
    ErrorResponse,
    NoProposalResponse,
    ProposalResponse,
    ReviewRequest,
)
from app.review.settings import ReviewRuntimeSettings
from tests.review.fakes import claim_for_case, proposal_input

# written by this release's worker; the next release's runtime must still accept it
SAVED_REQUEST = Path(__file__).parent / "data" / "runtime_request.json"


def duplicate(**changes: object) -> PossibleClaimDuplicate:
    fields: dict[str, object] = {
        "claim_id": uuid.uuid4(),
        "vendor_name": "Trattoria Lungolago",
        "vendor_tax_id": None,
        "document_number": "TL-88213",
        "document_date": date(2026, 8, 20),
        "total": Decimal("240.00"),
        "currency": "EUR",
        "status": "in_review",
        "same_employee": False,
        "same_file": True,
    }
    return PossibleClaimDuplicate(**(fields | changes))  # type: ignore[arg-type]


def training_claim() -> TrainingClaim:
    return TrainingClaim(uuid.uuid4(), date(2026, 3, 2), Decimal("120.00"), "EUR", "approved")


def test_a_request_survives_the_json_round_trip() -> None:
    claim = claim_for_case(
        "D03",
        warnings=[{"code": "sum_mismatch", "message": "The items don't add up."}],
        document_sha256="a" * 64,
        answered_requests=[AnsweredRequest(["attendees"], None, "Meridian Health")],
    )
    request = ReviewRequest(
        claim=claim, possible_duplicates=[duplicate()], training_claims=[training_claim()]
    )

    parsed = ReviewRequest.model_validate_json(request.model_dump_json())

    assert parsed == request
    assert parsed.claim == claim
    assert parsed.claim.days_to_submission == claim.days_to_submission


def test_a_saved_request_from_the_previous_release_still_parses() -> None:
    request = ReviewRequest.model_validate_json(SAVED_REQUEST.read_text("utf-8"))

    assert request.claim.claim_id == uuid.UUID("3f1c2a5e-8d4b-4c1e-9a7f-1b2c3d4e5f60")
    assert request.claim.expense.total == Decimal("240.00")
    assert request.claim.answered_requests[0].employee_answer == "Meridian Health"
    assert [d.document_number for d in request.possible_duplicates] == ["R-1001"]
    assert [t.total for t in request.training_claims] == [Decimal("120.00")]


@pytest.mark.parametrize(
    "response",
    [
        ProposalResponse(
            proposal=ReviewProposal.model_validate(proposal_input()),
            retrieved_clauses=["2.1", "2.3"],
            model="eu.model",
            usage=TokenUsage(1200, 300),
        ),
        NoProposalResponse(detail="no valid proposal, stop reason end_turn", usage=TokenUsage(9)),
        ErrorResponse(usage=TokenUsage(40, 2)),
    ],
    ids=["proposal", "no_proposal", "error"],
)
def test_each_response_parses_back_by_its_outcome(
    response: ProposalResponse | NoProposalResponse | ErrorResponse,
) -> None:
    assert REVIEW_RESPONSE.validate_json(response.model_dump_json()) == response


def test_an_unknown_outcome_is_refused() -> None:
    with pytest.raises(ValidationError):
        REVIEW_RESPONSE.validate_json('{"outcome": "maybe", "usage": {}}')


async def test_the_prefetched_history_answers_with_the_lists_it_was_given() -> None:
    duplicates, training = [duplicate()], [training_claim()]
    history = PrefetchedHistory(duplicates, training)
    claim = claim_for_case("D03")

    assert await history.find_possible_duplicates(claim) == duplicates
    assert await history.list_training_claims(claim) == training


def test_the_runtime_needs_no_database_cognito_or_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["DATABASE_URL", "COGNITO_USER_POOL_ID", "REVIEW_QUEUE_URL"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_REGION", "eu-north-1")
    monkeypatch.setenv("REVIEW_MODEL_ID", "eu.model")
    monkeypatch.setenv("POLICY_KB_ID", "KB123")

    settings = ReviewRuntimeSettings(_env_file=None)

    assert (settings.review_max_turns, settings.review_max_proposal_attempts) == (12, 3)
    assert settings.log_level == "INFO"


@pytest.mark.parametrize("name", ["AWS_REGION", "REVIEW_MODEL_ID", "POLICY_KB_ID"])
def test_the_runtime_refuses_an_empty_region_model_or_kb(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "")

    with pytest.raises(ValidationError, match=name.lower()):
        ReviewRuntimeSettings(_env_file=None)

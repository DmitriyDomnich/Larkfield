"""Decision, answer and review history endpoints without a database: roles, validation and
the OpenAPI document."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_token_verifier
from app.core.config import Settings
from app.review.schemas import AnswerCreate, ExpenseCorrections
from tests.claims.fakes import auth
from tests.tokens import make_verifier

CLAIM = "/claims/00000000-0000-0000-0000-000000000000"


@pytest.fixture
def api(client: TestClient, settings: Settings) -> TestClient:
    client.app.dependency_overrides[get_token_verifier] = lambda: make_verifier(settings)  # type: ignore[attr-defined]
    return client


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", f"{CLAIM}/decision", {"decision": "approve"}),
        ("POST", f"{CLAIM}/answer", {"message": "The attendees were A and B."}),
        ("GET", f"{CLAIM}/review", None),
    ],
)
def test_review_endpoints_need_a_token_and_are_closed_to_admins(
    api: TestClient, settings: Settings, method: str, path: str, body: Any
) -> None:
    assert api.request(method, path, json=body).status_code == 401
    admin = auth(settings, sub="admin-1", role="admin")
    assert api.request(method, path, json=body, headers=admin).status_code == 403


def test_only_reviewers_decide(api: TestClient, settings: Settings) -> None:
    response = api.post(
        f"{CLAIM}/decision", json={"decision": "approve"}, headers=auth(settings, role="employee")
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"decision": "maybe"}, id="unknown-decision"),
        pytest.param({}, id="no-decision"),
        pytest.param({"decision": "approve", "status": "approved"}, id="extra-field"),
        pytest.param({"decision": "approve", "comment": "x" * 2001}, id="comment-too-long"),
        pytest.param(
            {"decision": "approve", "corrected_fields": {"amount": "10.00"}}, id="unknown-field"
        ),
        pytest.param(
            {"decision": "approve", "corrected_fields": {"total": None}}, id="total-cleared"
        ),
        pytest.param({"decision": "approve", "corrected_fields": {"total": "0"}}, id="total-zero"),
        pytest.param(
            {"decision": "approve", "corrected_fields": {"currency": "eur"}}, id="bad-currency"
        ),
        pytest.param(
            {"decision": "approve", "corrected_fields": {"category": "luxury"}},
            id="bad-category",
        ),
    ],
)
def test_invalid_decision_is_422(api: TestClient, settings: Settings, body: Any) -> None:
    response = api.post(f"{CLAIM}/decision", json=body, headers=auth(settings, role="reviewer"))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="no-message"),
        pytest.param({"message": "   "}, id="blank-message"),
        pytest.param({"message": "x" * 1001}, id="message-too-long"),
        pytest.param({"message": "Updated.", "purpose": "short"}, id="purpose-too-short"),
        pytest.param({"message": "Updated.", "purpose": None}, id="purpose-cleared"),
        pytest.param({"message": "Updated.", "attendees": None}, id="attendees-cleared"),
        pytest.param(
            {"message": "Updated.", "attendees": [{"name": "J. Weber"}]}, id="attendee-no-company"
        ),
        pytest.param({"message": "Updated.", "preapproval_ref": "PA-26-1"}, id="bad-ref"),
        pytest.param({"message": "Updated.", "status": "extracted"}, id="extra-field"),
    ],
)
def test_invalid_answer_is_422(api: TestClient, settings: Settings, body: Any) -> None:
    response = api.post(f"{CLAIM}/answer", json=body, headers=auth(settings))

    assert response.status_code == 422


def test_corrections_keep_only_the_fields_sent_and_may_clear_nullable_ones() -> None:
    corrections = ExpenseCorrections.model_validate({"total": "42.50", "tip_amount": None})

    assert corrections.dump_corrected_fields() == {"total": "42.50", "tip_amount": None}
    assert ExpenseCorrections().dump_corrected_fields() is None


def test_an_answer_changes_only_the_claim_fields_it_sends() -> None:
    attendees = [{"name": "J. Weber", "company": "Meridian Health"}]

    assert AnswerCreate(message="See attendees.", attendees=attendees).dump_claim_changes() == {
        "attendees": attendees
    }
    assert AnswerCreate(message="Explained.").dump_claim_changes() == {}
    assert AnswerCreate.model_validate(
        {"message": "No reference.", "preapproval_ref": None}
    ).dump_claim_changes() == {"preapproval_ref": None}


def test_openapi_documents_every_review_endpoint(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]

    expected = {
        ("/claims/{claim_id}/decision", "post"): {"201", "401", "403", "404", "409", "422"},
        ("/claims/{claim_id}/answer", "post"): {"201", "401", "403", "404", "409", "422"},
        ("/claims/{claim_id}/review", "get"): {"200", "401", "403", "404"},
    }
    for (path, method), codes in expected.items():
        operation = paths[path][method]
        assert operation["summary"]
        assert codes <= set(operation["responses"]), (path, method)

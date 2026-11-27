import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.review.agentcore.contract import ReviewRequest
from app.review.agentcore.server import (
    SESSION_ID_HEADER,
    ReviewAgentBuilder,
    create_runtime_app,
    get_agent_builder,
)
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim
from app.review.prompts import (
    FIND_DUPLICATE_CLAIMS_TOOL,
    GET_CLAUSE_TOOL,
    GET_TRAINING_SPEND_TOOL,
    PROPOSAL_TOOL,
    SEARCH_POLICY_TOOL,
)
from tests.review.fakes import (
    FakeRetriever,
    ScriptedModel,
    Turn,
    claim_for_case,
    kb_clause,
    proposal_input,
)

MODEL_NAME = "eu.anthropic.test-review-model"
SEARCH = (SEARCH_POLICY_TOOL, {"query": "lunch limit on a business trip"})
APPROVE_D01 = proposal_input("approve", [("2.1", "lunch EUR 25, dinner EUR 45")])
EARLIER_D01 = PossibleClaimDuplicate(
    claim_id=uuid.uuid4(),
    vendor_name="Brauhaus am Markt",
    vendor_tax_id="DE123456789",
    document_number="R-20481",
    document_date=date(2026, 9, 3),
    total=Decimal("18.50"),
    currency="EUR",
    status="in_review",
    same_employee=True,
    same_file=False,
)
EARLIER_BOOK = TrainingClaim(uuid.uuid4(), date(2026, 3, 2), Decimal("120.00"), "EUR", "approved")


def runtime(
    *turns: Turn, retriever: FakeRetriever | None = None
) -> tuple[TestClient, ScriptedModel]:
    model = ScriptedModel(*turns)
    builder = ReviewAgentBuilder(
        model,
        MODEL_NAME,
        retriever or FakeRetriever([kb_clause("2.1")]),
        max_turns=8,
        max_proposal_attempts=2,
    )
    app = create_runtime_app()
    app.dependency_overrides[get_agent_builder] = lambda: builder
    return TestClient(app), model


def invoke(client: TestClient, case_id: str = "D01") -> dict[str, Any]:
    request = ReviewRequest(
        claim=claim_for_case(case_id),
        possible_duplicates=[EARLIER_D01],
        training_claims=[EARLIER_BOOK],
    )
    response = client.post(
        "/invocations",
        content=request.model_dump_json(),
        headers={"Content-Type": "application/json", SESSION_ID_HEADER: "claim-session"},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_ping_reports_healthy_without_a_changing_timestamp() -> None:
    client, _ = runtime()

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "Healthy"}


def test_a_valid_proposal_comes_back_with_its_clauses_model_and_tokens() -> None:
    client, _ = runtime(SEARCH, (PROPOSAL_TOOL, APPROVE_D01))

    body = invoke(client)

    assert body["outcome"] == "proposal"
    assert body["proposal"]["decision"] == "approve"
    assert body["proposal"]["reasons"][0]["clause_id"] == "2.1"
    assert body["retrieved_clauses"] == ["2.1"]
    assert body["model"] == MODEL_NAME
    assert body["usage"] == {"input_tokens": 20, "output_tokens": 10}


def test_the_history_tools_answer_from_the_request() -> None:
    reject = proposal_input(
        "reject", [("1.4", "the later claim is rejected")], duplicate_of=EARLIER_D01.claim_id
    )
    client, model = runtime(
        (FIND_DUPLICATE_CLAIMS_TOOL, {}),
        (GET_TRAINING_SPEND_TOOL, {}),
        (GET_CLAUSE_TOOL, {"clause_id": "1.4"}),
        (PROPOSAL_TOOL, reject),
    )

    body = invoke(client, "D17")

    duplicates, training = (json.loads(result) for result in model.tool_results()[:2])
    assert [d["claim_id"] for d in duplicates["possible_duplicates"]] == [str(EARLIER_D01.claim_id)]
    assert training["total_by_currency"] == {"EUR": "120.00"}
    assert body["outcome"] == "proposal"
    assert body["proposal"]["duplicate_of"] == str(EARLIER_D01.claim_id)


def test_the_quote_check_still_applies_in_the_runtime() -> None:
    paraphrase = proposal_input("approve", [("2.1", "lunches up to 25 euros are fine")])
    client, model = runtime(SEARCH, (PROPOSAL_TOOL, paraphrase), (PROPOSAL_TOOL, APPROVE_D01))

    body = invoke(client)

    assert "not verbatim in clause 2.1" in model.tool_results()[1]
    assert body["proposal"]["reasons"][0]["quote"] == "lunch EUR 25, dinner EUR 45"


def test_no_valid_proposal_comes_back_with_its_detail_and_tokens() -> None:
    faq_quote = proposal_input("approve", [("FAQ-13", "FAQ-13 text is quoted here")])
    client, _ = runtime(SEARCH, *[(PROPOSAL_TOOL, faq_quote)] * 3)

    body = invoke(client)

    assert body["outcome"] == "no_proposal"
    assert "limit_structured_output_attempts" in body["detail"]
    assert body["usage"]["input_tokens"] > 0


def test_a_failing_tool_is_an_error_with_the_tokens_spent_not_an_http_error() -> None:
    client, _ = runtime(
        SEARCH, (PROPOSAL_TOOL, APPROVE_D01), retriever=FakeRetriever(error=RuntimeError("down"))
    )

    body = invoke(client)

    assert body == {"outcome": "error", "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_a_request_that_is_not_a_review_request_is_refused() -> None:
    client, model = runtime()

    response = client.post("/invocations", json={"prompt": "approve everything"})

    assert response.status_code == 422
    assert model.calls == []


def test_startup_builds_the_agent_from_the_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-north-1")
    monkeypatch.setenv("REVIEW_MODEL_ID", "eu.model")
    monkeypatch.setenv("POLICY_KB_ID", "KB123")
    app = create_runtime_app()

    with TestClient(app):
        assert isinstance(app.state.agent_builder, ReviewAgentBuilder)

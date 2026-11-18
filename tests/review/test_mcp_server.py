import json
import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from mcp.client.client import Client
from mcp.types import CallToolResult, TextContent

from app.review.agent import CLAIM_TOOLS, ReviewRun
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim
from app.review.mcp_server import CLAIM_ID_PARAM, ReviewTools, build_server
from app.review.prompts import (
    FIND_DUPLICATE_CLAIMS_TOOL,
    GET_CLAUSE_TOOL,
    GET_TRAINING_SPEND_TOOL,
    SEARCH_POLICY_TOOL,
)
from tests.review.fakes import FakeHistory, FakeRetriever, claim_for_case, kb_clause

CLAIM = claim_for_case("D01")


def review_tools(
    retriever: FakeRetriever | None = None, history: FakeHistory | None = None
) -> ReviewTools:
    claims = {CLAIM.claim_id: CLAIM}

    async def load_claim(claim_id: uuid.UUID) -> ClaimUnderReview | None:
        return claims.get(claim_id)

    return ReviewTools(retriever or FakeRetriever(), history or FakeHistory(), load_claim)


async def call(tools: ReviewTools, name: str, **arguments: Any) -> CallToolResult:
    async with Client(build_server(tools)) as client:
        return await client.call_tool(name, arguments)


def text(result: CallToolResult) -> str:
    return cast(TextContent, result.content[0]).text


async def test_the_server_lists_the_agent_tools_with_a_claim_id_on_the_claim_tools() -> None:
    agent_tools = ReviewRun(CLAIM, FakeRetriever(), FakeHistory()).tools()

    async with Client(build_server(review_tools())) as client:
        listed = (await client.list_tools()).tools

    assert [tool.name for tool in listed] == [
        SEARCH_POLICY_TOOL,
        GET_CLAUSE_TOOL,
        FIND_DUPLICATE_CLAIMS_TOOL,
        GET_TRAINING_SPEND_TOOL,
    ]
    for tool, agent_tool in zip(listed, agent_tools, strict=True):
        agent_schema = agent_tool.tool_spec["inputSchema"]["json"]
        assert tool.description == agent_tool.tool_spec["description"]
        claim_param = {CLAIM_ID_PARAM} if tool.name in CLAIM_TOOLS else set()
        assert set(tool.input_schema.get("required", [])) == {
            *claim_param,
            *agent_schema.get("required", []),
        }
        assert set(tool.input_schema["properties"]) == {
            *claim_param,
            *agent_schema.get("properties", {}),
        }
    assert {FIND_DUPLICATE_CLAIMS_TOOL, GET_TRAINING_SPEND_TOOL} == CLAIM_TOOLS


async def test_search_policy_needs_no_claim_and_returns_what_the_agent_gets() -> None:
    retriever = FakeRetriever(results=[kb_clause("2.1")])

    result = await call(review_tools(retriever), SEARCH_POLICY_TOOL, query="meal limits")

    assert not result.is_error
    assert retriever.queries == ["meal limits"]
    [chunk] = json.loads(text(result))
    assert chunk["clause_id"] == "2.1"
    assert chunk["binding"] is True


async def test_get_clause_reports_a_clause_that_does_not_exist() -> None:
    result = await call(review_tools(), GET_CLAUSE_TOOL, clause_id="99.9")

    assert not result.is_error
    assert text(result) == "There is no binding clause '99.9'."


async def test_find_duplicate_claims_runs_for_the_given_claim() -> None:
    duplicate = PossibleClaimDuplicate(
        claim_id=uuid.uuid4(),
        vendor_name="Cafe Rot",
        vendor_tax_id=None,
        document_number="A-1",
        document_date=date(2026, 3, 2),
        total=Decimal("42.50"),
        currency="EUR",
        status="in_review",
        same_employee=True,
        same_file=False,
    )

    result = await call(
        review_tools(history=FakeHistory(duplicates=[duplicate])),
        FIND_DUPLICATE_CLAIMS_TOOL,
        claim_id=str(CLAIM.claim_id),
    )

    found = json.loads(text(result))["possible_duplicates"]
    assert [claim["claim_id"] for claim in found] == [str(duplicate.claim_id)]


@pytest.mark.parametrize("arguments", [{"claim_id": "claim-1"}, {}])
async def test_a_claim_tool_without_a_claim_id_is_an_error(arguments: dict[str, Any]) -> None:
    result = await call(review_tools(), GET_TRAINING_SPEND_TOOL, **arguments)

    assert result.is_error
    assert CLAIM_ID_PARAM in text(result)


async def test_an_unknown_claim_is_an_error() -> None:
    result = await call(review_tools(), GET_TRAINING_SPEND_TOOL, claim_id=str(uuid.uuid4()))

    assert result.is_error
    assert "no claim" in text(result)


async def test_an_unknown_tool_is_an_error() -> None:
    result = await call(review_tools(), "approve_claim")

    assert result.is_error
    assert "approve_claim" in text(result)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [(SEARCH_POLICY_TOOL, {"question": "meals"}), (GET_CLAUSE_TOOL, {"clause_id": 7.1})],
)
async def test_wrong_arguments_get_the_validation_error_the_agent_gets(
    name: str, arguments: dict[str, Any]
) -> None:
    retriever = FakeRetriever()

    result = await call(review_tools(retriever), name, **arguments)

    assert result.is_error
    assert "Validation failed" in text(result)
    assert retriever.queries == retriever.clause_ids == []


async def test_an_error_inside_a_tool_is_logged_and_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = TrainingClaim(uuid.uuid4(), date(2026, 3, 2), cast(Decimal, None), "EUR", "approved")
    tools = review_tools(history=FakeHistory(training=[broken]))

    with caplog.at_level(logging.ERROR):
        result = await call(tools, GET_TRAINING_SPEND_TOOL, claim_id=str(CLAIM.claim_id))

    assert result.is_error
    assert "TypeError" in text(result)
    assert f"tool {GET_TRAINING_SPEND_TOOL} failed" in caplog.text


async def test_a_failed_lookup_is_an_error_without_the_exception_text() -> None:
    retriever = FakeRetriever(error=RuntimeError("secret endpoint detail"))

    result = await call(review_tools(retriever), SEARCH_POLICY_TOOL, query="meals")

    assert result.is_error
    assert "RuntimeError" in text(result)
    assert "secret endpoint detail" not in text(result)

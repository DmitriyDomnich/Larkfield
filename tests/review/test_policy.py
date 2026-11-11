from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

from app.review.policy import (
    EMPLOYEE_AUDIENCE_FILTER,
    SEARCH_RESULTS_COUNT,
    BedrockPolicyRetriever,
    PolicyChunk,
)
from tests.review.fakes import EXPENSE_CLAUSES, EXPENSE_POLICY, kb_clause

KB_ID = "KBCLAUSE01"
CLAUSE_2_3_FILTER = {
    "andAll": [
        {"equals": {"key": "clause_id", "value": "2.3"}},
        {"equals": {"key": "binding", "value": True}},
    ]
}


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")


@pytest.fixture
def stubbed() -> Iterator[tuple[BedrockPolicyRetriever, Stubber]]:
    client = boto3.client("bedrock-agent-runtime", region_name="eu-central-1")
    with Stubber(client) as stubber:
        yield BedrockPolicyRetriever(KB_ID, "eu-central-1", client=client), stubber
        stubber.assert_no_pending_responses()


def kb_result(text: str, **metadata: Any) -> dict[str, Any]:
    return {"content": {"text": text}, "score": 0.5, "metadata": metadata}


def retrieve_request(query: str, results: int, retrieval_filter: Any) -> dict[str, Any]:
    return {
        "knowledgeBaseId": KB_ID,
        "retrievalQuery": {"text": query},
        "retrievalConfiguration": {
            "vectorSearchConfiguration": {"numberOfResults": results, "filter": retrieval_filter}
        },
    }


async def test_search_asks_for_the_top_results_without_contractor_clauses(
    stubbed: tuple[BedrockPolicyRetriever, Stubber],
) -> None:
    retriever, stubber = stubbed
    stubber.add_response(
        "retrieve",
        {
            "retrievalResults": [
                kb_result(
                    "FAQ text",
                    clause_id="FAQ-13",
                    document="employee-expenses-faq",
                    binding=False,
                    references=["2.1", "7.1"],
                ),
                kb_result("2.1 text", clause_id="2.1", document=EXPENSE_POLICY, binding=True),
            ]
        },
        retrieve_request(
            "dinner limit on a business trip", SEARCH_RESULTS_COUNT, EMPLOYEE_AUDIENCE_FILTER
        ),
    )

    chunks = await retriever.search("dinner limit on a business trip")

    assert chunks == [
        PolicyChunk("FAQ-13", "employee-expenses-faq", "FAQ text", ("2.1", "7.1")),
        PolicyChunk("2.1", EXPENSE_POLICY, "2.1 text", binding=True),
    ]
    assert [chunk.binding for chunk in chunks] == [False, True]


async def test_a_single_reference_and_missing_metadata_are_read(
    stubbed: tuple[BedrockPolicyRetriever, Stubber],
) -> None:
    retriever, stubber = stubbed
    stubber.add_response(
        "retrieve",
        {"retrievalResults": [kb_result("a", references="1.3"), {"content": {"text": "b"}}]},
    )

    chunks = await retriever.search("card slip")

    assert chunks[0].references == ("1.3",)
    assert chunks[1] == PolicyChunk("", "", "b")


async def test_a_clause_by_id_is_one_expense_policy_chunk_filtered_on_its_id(
    stubbed: tuple[BedrockPolicyRetriever, Stubber],
) -> None:
    retriever, stubber = stubbed
    expected = kb_clause("2.3")
    stubber.add_response(
        "retrieve",
        {
            "retrievalResults": [
                kb_result(expected.text, clause_id="2.3", document=EXPENSE_POLICY, binding=True)
            ]
        },
        retrieve_request("2.3", 1, CLAUSE_2_3_FILTER),
    )

    assert await retriever.clause("2.3") == expected


@pytest.mark.parametrize(
    "results",
    [[], [kb_result("2.2 text", clause_id="2.2", document=EXPENSE_POLICY)]],
)
async def test_no_clause_when_the_kb_has_none_with_that_id(
    stubbed: tuple[BedrockPolicyRetriever, Stubber], results: list[dict[str, Any]]
) -> None:
    retriever, stubber = stubbed
    stubber.add_response("retrieve", {"retrievalResults": results})

    assert await retriever.clause("2.3") is None


def test_clause_text_is_the_clause_without_the_document_line() -> None:
    chunk = kb_clause("7.2")

    assert chunk.text.startswith("Expense Policy: 7. Decisions\n\n**7.2 Missing information.**")
    assert chunk.clause_text == EXPENSE_CLAUSES["7.2"].text


def test_a_chunk_without_its_clause_heading_has_no_clause_text() -> None:
    piece = PolicyChunk("2.1", EXPENSE_POLICY, "a piece of 2.1 without its heading")

    assert piece.clause_text is None


@pytest.mark.parametrize(("value", "binding"), [(True, True), ("true", True), (False, False)])
async def test_binding_comes_from_the_document_metadata(
    stubbed: tuple[BedrockPolicyRetriever, Stubber], value: object, binding: bool
) -> None:
    """Any document marked binding counts, not only the Expense Policy"""
    retriever, stubber = stubbed
    stubber.add_response(
        "retrieve",
        {
            "retrievalResults": [
                kb_result("x", clause_id="X1.1", document="new-policy", binding=value)
            ]
        },
    )

    [chunk] = await retriever.search("anything")

    assert chunk.binding is binding

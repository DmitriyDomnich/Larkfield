import json
import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.review.agent import (
    NoValidProposal,
    StrandsReviewAgent,
    ToolFailedError,
    ValidProposal,
)
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim
from app.review.models import Decision
from app.review.policy import PolicyChunk
from app.review.prompts import (
    CLAIM_DATA_TAG,
    FIND_DUPLICATE_CLAIMS_TOOL,
    GET_CLAUSE_TOOL,
    GET_TRAINING_SPEND_TOOL,
    PROPOSAL_TOOL,
    SEARCH_POLICY_TOOL,
)
from tests.review.fakes import (
    EXPENSE_CLAUSES,
    FakeHistory,
    FakeRetriever,
    ScriptedModel,
    Turn,
    claim_for_case,
    kb_clause,
    proposal_input,
)

MODEL_NAME = "eu.anthropic.test-review-model"
FAQ_13 = PolicyChunk("FAQ-13", "employee-expenses-faq", "FAQ-13 text", ("2.1", "7.1"))
IT_2_3 = PolicyChunk("IT2.3", "it-equipment-procurement-policy", "IT2.3 text", ("4.1",))
# the default search finds the FAQ entry and clause 2.1
SEARCH = (SEARCH_POLICY_TOOL, {"query": "lunch limit on a business trip"})
APPROVE_D01 = proposal_input("approve", [("2.1", "lunch EUR 25, dinner EUR 45")])
DUPLICATE_REASON = ("1.4", "the later claim is rejected")


def make_agent(
    *turns: Turn,
    retriever: FakeRetriever | None = None,
    history: FakeHistory | None = None,
    max_turns: int = 8,
    max_proposal_attempts: int = 2,
) -> tuple[StrandsReviewAgent, ScriptedModel]:
    model = ScriptedModel(*turns)
    agent = StrandsReviewAgent(
        model,
        MODEL_NAME,
        retriever or FakeRetriever([FAQ_13, kb_clause("2.1")]),
        history or FakeHistory(),
        max_turns=max_turns,
        max_proposal_attempts=max_proposal_attempts,
    )
    return agent, model


async def test_the_agent_consults_the_tools_and_returns_a_valid_proposal() -> None:
    agent, model = make_agent(
        SEARCH,
        (GET_CLAUSE_TOOL, {"clause_id": "1.2"}),
        (FIND_DUPLICATE_CLAIMS_TOOL, {}),
        (PROPOSAL_TOOL, APPROVE_D01),
    )

    outcome = await agent.review(claim_for_case("D01"))

    assert isinstance(outcome, ValidProposal)
    assert outcome.proposal.decision is Decision.APPROVE
    assert outcome.proposal.reasons[0].clause_id == "2.1"
    assert outcome.model == MODEL_NAME
    assert outcome.retrieved_clauses == ["FAQ-13", "2.1", "1.2"]

    search, clause, duplicates = model.tool_results()
    faq, clause_2_1 = json.loads(search)
    assert (faq["clause_id"], faq["binding"]) == ("FAQ-13", False)
    assert faq["references"] == ["2.1", "7.1"]
    assert (clause_2_1["clause_id"], clause_2_1["binding"]) == ("2.1", True)
    assert json.loads(clause)[0]["text"] == kb_clause("1.2").text
    assert json.loads(duplicates) == {"possible_duplicates": []}


async def test_a_referenced_clause_is_fetched_from_the_kb_by_id_and_can_be_cited() -> None:
    """FAQ-13 names 7.1; the agent follows the reference with get_clause"""
    retriever = FakeRetriever([FAQ_13])
    reject = proposal_input(
        "reject", [("7.1", "A claim that exceeds a limit in this policy is rejected as a whole")]
    )
    agent, _ = make_agent(
        SEARCH,
        (GET_CLAUSE_TOOL, {"clause_id": " 7.1 "}),
        (PROPOSAL_TOOL, reject),
        retriever=retriever,
    )

    outcome = await agent.review(claim_for_case("D02"))

    assert isinstance(outcome, ValidProposal)
    assert retriever.clause_ids == ["7.1"]
    assert outcome.retrieved_clauses == ["FAQ-13", "7.1"]


async def test_a_clause_that_was_not_retrieved_is_refused_until_fetched() -> None:
    agent, model = make_agent(
        (PROPOSAL_TOOL, APPROVE_D01),
        (GET_CLAUSE_TOOL, {"clause_id": "2.1"}),
        (PROPOSAL_TOOL, APPROVE_D01),
    )

    outcome = await agent.review(claim_for_case("D01"))

    assert isinstance(outcome, ValidProposal)
    refused = model.tool_results()[0]
    assert "'2.1' is not a binding clause retrieved in this review" in refused


async def test_the_model_gets_the_claim_as_data_and_only_the_review_tools() -> None:
    agent, model = make_agent(SEARCH, (PROPOSAL_TOOL, APPROVE_D01))

    await agent.review(claim_for_case("D14"))

    first = model.calls[0]
    assert sorted(first.tool_names) == sorted(
        [
            SEARCH_POLICY_TOOL,
            GET_CLAUSE_TOOL,
            FIND_DUPLICATE_CLAIMS_TOOL,
            GET_TRAINING_SPEND_TOOL,
            PROPOSAL_TOOL,
        ]
    )
    [user_message] = first.messages
    text = user_message["content"][0]["text"]
    assert text.startswith(f"Review this claim.\n<{CLAIM_DATA_TAG}>")
    assert "pre-approved by Finance" in text


async def test_a_text_answer_is_never_a_proposal_the_proposal_tool_is_forced() -> None:
    agent, model = make_agent(
        SEARCH, "This claim looks fine, approve.", (PROPOSAL_TOOL, APPROVE_D01)
    )

    outcome = await agent.review(claim_for_case("D01"))

    assert isinstance(outcome, ValidProposal)
    assert model.calls[2].tool_choice == {"tool": {"name": PROPOSAL_TOOL}}


async def test_an_invalid_quote_is_sent_back_and_the_corrected_proposal_kept() -> None:
    paraphrase = proposal_input("approve", [("2.1", "lunches up to 25 euros are fine")])
    agent, model = make_agent(SEARCH, (PROPOSAL_TOOL, paraphrase), (PROPOSAL_TOOL, APPROVE_D01))

    outcome = await agent.review(claim_for_case("D01"))

    assert isinstance(outcome, ValidProposal)
    assert outcome.proposal.reasons[0].quote == "lunch EUR 25, dinner EUR 45"
    assert "not verbatim in clause 2.1" in model.tool_results()[1]


async def test_a_quote_from_a_non_binding_result_is_refused() -> None:
    """FAQ-13 was retrieved, but only the Expense Policy may justify a decision"""
    faq_quote = proposal_input("approve", [("FAQ-13", "FAQ-13 text is quoted here")])
    agent, _ = make_agent(SEARCH, *[(PROPOSAL_TOOL, faq_quote)] * 3, max_proposal_attempts=2)

    outcome = await agent.review(claim_for_case("D01"))

    assert isinstance(outcome, NoValidProposal)
    assert "limit_structured_output_attempts" in outcome.detail


async def test_no_valid_proposal_within_the_turn_limit() -> None:
    agent, model = make_agent(*[SEARCH] * 3, max_turns=3)

    outcome = await agent.review(claim_for_case("D01"))

    assert isinstance(outcome, NoValidProposal)
    assert "limit_turns" in outcome.detail
    assert len(model.calls) == 3


@pytest.mark.parametrize("failing_turn", [SEARCH, (GET_CLAUSE_TOOL, {"clause_id": "2.1"})])
async def test_a_failing_knowledge_base_stops_the_review(failing_turn: Turn) -> None:
    agent, model = make_agent(
        failing_turn,
        (PROPOSAL_TOOL, APPROVE_D01),
        retriever=FakeRetriever(error=RuntimeError("throttled")),
    )

    with pytest.raises(ToolFailedError):
        await agent.review(claim_for_case("D01"))

    assert len(model.calls) == 1


async def test_a_failing_claims_history_stops_the_review() -> None:
    agent, _ = make_agent(
        (FIND_DUPLICATE_CLAIMS_TOOL, {}),
        (PROPOSAL_TOOL, APPROVE_D01),
        history=FakeHistory(error=RuntimeError("database down")),
    )

    with pytest.raises(ToolFailedError):
        await agent.review(claim_for_case("D01"))


async def test_a_duplicate_found_by_the_tool_can_be_named() -> None:
    """D17: same vendor, date and total as D01"""
    earlier = PossibleClaimDuplicate(
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
    reject = proposal_input("reject", [DUPLICATE_REASON], duplicate_of=earlier.claim_id)
    agent, model = make_agent(
        (FIND_DUPLICATE_CLAIMS_TOOL, {}),
        (GET_CLAUSE_TOOL, {"clause_id": "1.4"}),
        (PROPOSAL_TOOL, reject),
        history=FakeHistory(duplicates=[earlier]),
    )

    outcome = await agent.review(claim_for_case("D17"))

    assert isinstance(outcome, ValidProposal)
    assert outcome.proposal.duplicate_of == earlier.claim_id
    [found] = json.loads(model.tool_results()[0])["possible_duplicates"]
    assert found["claim_id"] == str(earlier.claim_id)
    assert found["total"] == "18.50"
    assert "purpose" not in found
    assert "employee_sub" not in found


async def test_a_duplicate_the_tool_did_not_find_is_refused() -> None:
    reject = proposal_input("reject", [DUPLICATE_REASON], duplicate_of=uuid.uuid4())
    agent, model = make_agent(
        (GET_CLAUSE_TOOL, {"clause_id": "1.4"}),
        (PROPOSAL_TOOL, reject),
        SEARCH,
        (PROPOSAL_TOOL, APPROVE_D01),
    )

    outcome = await agent.review(claim_for_case("D17"))

    assert isinstance(outcome, ValidProposal)
    assert outcome.proposal.duplicate_of is None
    assert "find_duplicate_claims returned" in model.tool_results()[1]


async def test_get_clause_for_an_id_that_is_not_binding() -> None:
    agent, model = make_agent(
        (GET_CLAUSE_TOOL, {"clause_id": "C1.2"}), SEARCH, (PROPOSAL_TOOL, APPROVE_D01)
    )

    outcome = await agent.review(claim_for_case("D01"))

    assert model.tool_results()[0] == "There is no binding clause 'C1.2'."
    assert isinstance(outcome, ValidProposal)
    assert "C1.2" not in outcome.retrieved_clauses


async def test_training_spend_lists_the_years_claims_and_their_total() -> None:
    history = FakeHistory(
        training=[
            TrainingClaim(uuid.uuid4(), date(2026, 3, 1), Decimal("120.00"), "EUR", "approved"),
            TrainingClaim(uuid.uuid4(), date(2026, 6, 1), Decimal("300.50"), "EUR", "in_review"),
        ]
    )
    approve = proposal_input("approve", [("5.1", "reimbursed up to EUR 500 per calendar year")])
    agent, model = make_agent(
        (GET_TRAINING_SPEND_TOOL, {}),
        (GET_CLAUSE_TOOL, {"clause_id": "5.1"}),
        (PROPOSAL_TOOL, approve),
        history=history,
    )

    outcome = await agent.review(claim_for_case("D20"))

    assert isinstance(outcome, ValidProposal)
    spend = json.loads(model.tool_results()[0])
    assert spend["total_by_currency"] == {"EUR": "420.50"}
    assert [claim["status"] for claim in spend["earlier_training_claims"]] == [
        "approved",
        "in_review",
    ]


async def test_each_review_starts_with_a_fresh_conversation_and_retrievals() -> None:
    agent, model = make_agent(
        SEARCH,
        (PROPOSAL_TOOL, APPROVE_D01),
        (PROPOSAL_TOOL, APPROVE_D01),
        SEARCH,
        (PROPOSAL_TOOL, APPROVE_D01),
    )

    await agent.review(claim_for_case("D01"))
    second = await agent.review(claim_for_case("D02"))

    assert len(model.calls[2].messages) == 1
    assert "Hamburg trip, project Orion" in model.calls[2].messages[0]["content"][0]["text"]
    # 2.1 retrieved in the first review does not count for the second
    assert "is not a binding clause retrieved" in model.tool_results()[0]
    assert isinstance(second, ValidProposal)


async def test_the_search_results_include_other_documents_marked_not_binding() -> None:
    agent, model = make_agent(
        (SEARCH_POLICY_TOOL, {"query": "keyboard delivery"}),
        (GET_CLAUSE_TOOL, {"clause_id": "2.1"}),
        (PROPOSAL_TOOL, APPROVE_D01),
        retriever=FakeRetriever([IT_2_3]),
    )

    await agent.review(claim_for_case("D11"))

    assert json.loads(model.tool_results()[0]) == [
        {
            "clause_id": "IT2.3",
            "document": "it-equipment-procurement-policy",
            "binding": False,
            "text": "IT2.3 text",
            "references": ["4.1"],
        }
    ]


def test_every_expense_policy_clause_is_quotable_from_its_kb_chunk() -> None:
    for clause_id, clause in EXPENSE_CLAUSES.items():
        assert kb_clause(clause_id).clause_text == clause.text


async def test_each_search_query_is_logged_with_what_it_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    agent, _ = make_agent(SEARCH, (PROPOSAL_TOOL, APPROVE_D01))
    claim = claim_for_case("D01")

    with caplog.at_level(logging.INFO, logger="app.review.agent"):
        await agent.review(claim)

    assert (
        f"claim {claim.claim_id}: search_policy('lunch limit on a business trip') "
        "found ['FAQ-13', '2.1']"
    ) in caplog.messages


async def test_every_tool_call_is_logged_with_what_it_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    earlier = uuid.uuid4()
    history = FakeHistory(
        duplicates=[
            PossibleClaimDuplicate(
                earlier,
                "Brauhaus am Markt",
                None,
                None,
                date(2026, 9, 3),
                Decimal("18.50"),
                "EUR",
                "in_review",
                same_employee=True,
                same_file=False,
            )
        ],
        training=[
            TrainingClaim(uuid.uuid4(), date(2026, 3, 1), Decimal("120.00"), "EUR", "approved")
        ],
    )
    agent, _ = make_agent(
        (GET_CLAUSE_TOOL, {"clause_id": "7.1"}),
        (GET_CLAUSE_TOOL, {"clause_id": "C1.2"}),
        (FIND_DUPLICATE_CLAIMS_TOOL, {}),
        (GET_TRAINING_SPEND_TOOL, {}),
        SEARCH,
        (PROPOSAL_TOOL, APPROVE_D01),
        history=history,
    )
    claim = claim_for_case("D01")

    with caplog.at_level(logging.INFO, logger="app.review.agent"):
        await agent.review(claim)

    prefix = f"claim {claim.claim_id}: "
    assert caplog.messages[:4] == [
        prefix + "get_clause('7.1') found 7.1",
        prefix + "get_clause('C1.2') found nothing",
        prefix + f"find_duplicate_claims() found ['{earlier}']",
        prefix + "get_training_spend() found 1 claims, total 120.00 EUR",
    ]

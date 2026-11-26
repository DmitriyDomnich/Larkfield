import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ReadTimeoutError

from app.core.metrics import BedrockRunError, TokenUsage
from app.review.agent import NoValidProposal, ValidProposal
from app.review.agentcore import RUNTIME_CLIENT_CONFIG, AgentCoreClient
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim
from app.review.models import Decision
from app.review.proposal import ReviewProposal
from app.review.runtime_contract import (
    ErrorResponse,
    NoProposalResponse,
    ProposalResponse,
    RuntimeResponse,
)
from tests.review.fakes import (
    RUNTIME_ARN,
    FakeHistory,
    claim_for_case,
    proposal_input,
    runtime_answer,
    stubbed_runtime_client,
)

MODEL = "eu.anthropic.test-review-model"
EARLIER = PossibleClaimDuplicate(
    claim_id=uuid.uuid4(),
    vendor_name="Brauhaus am Markt",
    vendor_tax_id=None,
    document_number="R-20481",
    document_date=date(2026, 9, 3),
    total=Decimal("18.50"),
    currency="EUR",
    status="in_review",
    same_employee=True,
    same_file=False,
)
BOOK = TrainingClaim(uuid.uuid4(), date(2026, 3, 2), Decimal("120.00"), "EUR", "approved")
PROPOSAL = ProposalResponse(
    proposal=ReviewProposal.model_validate(proposal_input()),
    retrieved_clauses=["FAQ-13", "2.1"],
    model=MODEL,
    usage=TokenUsage(1200, 300),
)


class RuntimeCall:
    """A stubbed runtime that answers once and records the parameters it was called with"""

    def __init__(self, answer: RuntimeResponse | bytes | None = None, error_code: str = "") -> None:
        client, self.stubber = stubbed_runtime_client()
        self.params: dict[str, Any] = {}
        client.meta.events.register(
            "before-parameter-build.bedrock-agentcore.InvokeAgentRuntime", self._record
        )
        if error_code:
            self.stubber.add_client_error("invoke_agent_runtime", service_error_code=error_code)
        else:
            self.stubber.add_response("invoke_agent_runtime", runtime_answer(answer or PROPOSAL))
        self.stubber.activate()
        self.agent = AgentCoreClient(
            RUNTIME_ARN, FakeHistory([EARLIER], [BOOK]), "eu-north-1", client
        )

    def _record(self, params: dict[str, Any], **_: Any) -> None:
        self.params = params

    @property
    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.params["payload"])
        return result


async def test_the_claim_goes_with_both_history_lists_in_the_claims_own_session() -> None:
    call = RuntimeCall()
    claim = claim_for_case("D01")

    await call.agent.review(claim)

    call.stubber.assert_no_pending_responses()
    assert call.params["agentRuntimeArn"] == RUNTIME_ARN
    assert call.params["runtimeSessionId"] == str(claim.claim_id)
    assert call.params["contentType"] == "application/json"
    assert call.payload["claim"]["claim_id"] == str(claim.claim_id)
    assert call.payload["claim"]["expense"]["total"] == "18.50"
    assert [d["claim_id"] for d in call.payload["possible_duplicates"]] == [str(EARLIER.claim_id)]
    assert [t["total"] for t in call.payload["training_claims"]] == ["120.00"]


async def test_a_proposal_maps_to_a_valid_proposal_with_its_tokens() -> None:
    outcome = await RuntimeCall(PROPOSAL).agent.review(claim_for_case("D01"))

    assert isinstance(outcome, ValidProposal)
    assert outcome.proposal.decision is Decision.APPROVE
    assert outcome.retrieved_clauses == ["FAQ-13", "2.1"]
    assert outcome.model == MODEL
    assert outcome.usage == TokenUsage(1200, 300)


async def test_no_proposal_maps_to_no_valid_proposal_with_its_tokens() -> None:
    answer = NoProposalResponse(detail="stop reason limit_turns", usage=TokenUsage(90, 12))

    outcome = await RuntimeCall(answer).agent.review(claim_for_case("D01"))

    assert outcome == NoValidProposal("stop reason limit_turns")
    assert outcome.usage == TokenUsage(90, 12)


async def test_an_error_raises_with_the_tokens_the_runtime_spent() -> None:
    call = RuntimeCall(ErrorResponse(usage=TokenUsage(40, 2)))

    with pytest.raises(BedrockRunError) as raised:
        await call.agent.review(claim_for_case("D01"))

    assert raised.value.usage == TokenUsage(40, 2)


@pytest.mark.parametrize(
    "error_code",
    [
        "ThrottlingException",
        "AccessDeniedException",
        "RuntimeClientError",
        "InternalServerException",
    ],
)
async def test_a_failed_call_raises_with_no_tokens(error_code: str) -> None:
    call = RuntimeCall(error_code=error_code)

    with pytest.raises(BedrockRunError) as raised:
        await call.agent.review(claim_for_case("D01"))

    assert raised.value.usage == TokenUsage()
    assert error_code in str(raised.value.__cause__)


@pytest.mark.parametrize(
    "body", [b"not json", b'{"outcome": "maybe"}', b'{"outcome": "proposal"}'], ids=str
)
async def test_an_unparseable_body_raises_with_no_tokens(body: bytes) -> None:
    with pytest.raises(BedrockRunError) as raised:
        await RuntimeCall(body).agent.review(claim_for_case("D01"))

    assert raised.value.usage == TokenUsage()


async def test_a_timeout_raises_with_no_tokens() -> None:
    class TimingOutClient:
        def invoke_agent_runtime(self, **_: Any) -> Any:
            raise ReadTimeoutError(endpoint_url="https://bedrock-agentcore")

    client: Any = TimingOutClient()
    agent = AgentCoreClient(RUNTIME_ARN, FakeHistory(), "eu-north-1", client)

    with pytest.raises(BedrockRunError) as raised:
        await agent.review(claim_for_case("D01"))

    assert raised.value.usage == TokenUsage()


async def test_a_failing_history_lookup_is_not_sent_to_the_runtime() -> None:
    client, stubber = stubbed_runtime_client()
    stubber.activate()
    agent = AgentCoreClient(
        RUNTIME_ARN, FakeHistory(error=RuntimeError("database down")), "eu-north-1", client
    )

    with pytest.raises(RuntimeError, match="database down"):
        await agent.review(claim_for_case("D01"))


def test_one_attempt_and_the_15_minute_synchronous_limit() -> None:
    options = vars(RUNTIME_CLIENT_CONFIG)

    assert options["retries"] == {"total_max_attempts": 1, "mode": "standard"}
    assert options["read_timeout"] == 900

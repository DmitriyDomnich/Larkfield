import asyncio
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from app.core.metrics import BedrockRunError, TokenUsage
from app.review.agent import NoValidProposal, ReviewOutcome, ValidProposal
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import ClaimsHistory
from app.review.runtime_contract import (
    REVIEW_RESPONSE,
    ErrorResponse,
    NoProposalResponse,
    ProposalResponse,
    ReviewRequest,
)

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agentcore import BedrockAgentCoreClient

RUNTIME_CLIENT_CONFIG = Config(
    read_timeout=900, retries={"total_max_attempts": 1, "mode": "standard"}
)


class RuntimeReviewFailedError(BedrockRunError):
    def __init__(self, usage: TokenUsage) -> None:
        super().__init__(usage, "the agent runtime reported a failed review")


class AgentCoreClient:
    def __init__(
        self,
        runtime_arn: str,
        history: ClaimsHistory,
        region: str,
        client: "BedrockAgentCoreClient | None" = None,
    ) -> None:
        self._runtime_arn = runtime_arn
        self._history = history
        self._client = client or boto3.client(
            "bedrock-agentcore", region_name=region, config=RUNTIME_CLIENT_CONFIG
        )

    async def review(self, claim: ClaimUnderReview) -> ReviewOutcome:
        request = ReviewRequest(
            claim=claim,
            possible_duplicates=await self._history.find_possible_duplicates(claim),
            training_claims=await self._history.list_training_claims(claim),
        )
        try:
            body = await asyncio.to_thread(self._invoke, request)
            response = REVIEW_RESPONSE.validate_json(body)
        except Exception as exc:
            raise BedrockRunError(TokenUsage(), "invoking the agent runtime failed") from exc
        match response:
            case ProposalResponse():
                return ValidProposal(
                    response.proposal, response.retrieved_clauses, response.model, response.usage
                )
            case NoProposalResponse():
                return NoValidProposal(response.detail, response.usage)
            case ErrorResponse():
                raise RuntimeReviewFailedError(response.usage)

    def _invoke(self, request: ReviewRequest) -> bytes:
        response = self._client.invoke_agent_runtime(
            agentRuntimeArn=self._runtime_arn,
            runtimeSessionId=str(request.claim.claim_id),
            contentType="application/json",
            accept="application/json",
            payload=request.model_dump_json().encode(),
        )
        return response["response"].read()

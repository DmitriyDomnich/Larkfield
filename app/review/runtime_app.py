import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from botocore.config import Config
from fastapi import Depends, FastAPI, Header, Request
from strands.models.bedrock import BedrockModel
from strands.models.model import Model

from app.core.metrics import BedrockRunError, TokenUsage
from app.review.agent import (
    NoValidProposal,
    ReviewAgent,
    StrandsReviewAgent,
    ValidProposal,
)
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import ClaimsHistory, PrefetchedHistory
from app.review.policy import BedrockPolicyRetriever, PolicyRetriever
from app.review.runtime_contract import (
    ErrorResponse,
    NoProposalResponse,
    ProposalResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.review.settings import ReviewRuntimeSettings
from app.review.worker import MAX_OUTPUT_TOKENS

logger = logging.getLogger(__name__)

SESSION_ID_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"


class ReviewAgentBuilder:
    def __init__(
        self,
        model: Model,
        model_name: str,
        retriever: PolicyRetriever,
        *,
        max_turns: int,
        max_proposal_attempts: int,
    ) -> None:
        self._model = model
        self._model_name = model_name
        self._retriever = retriever
        self._max_turns = max_turns
        self._max_proposal_attempts = max_proposal_attempts

    def agent_for(self, history: ClaimsHistory) -> ReviewAgent:
        return StrandsReviewAgent(
            self._model,
            self._model_name,
            self._retriever,
            history,
            max_turns=self._max_turns,
            max_proposal_attempts=self._max_proposal_attempts,
        )


def build_agent_builder(settings: ReviewRuntimeSettings) -> ReviewAgentBuilder:
    return ReviewAgentBuilder(
        BedrockModel(
            model_id=settings.review_model_id,
            region_name=settings.aws_region,
            boto_client_config=Config(read_timeout=120),
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0,
        ),
        settings.review_model_id,
        BedrockPolicyRetriever(settings.policy_kb_id, settings.aws_region),
        max_turns=settings.review_max_turns,
        max_proposal_attempts=settings.review_max_proposal_attempts,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = ReviewRuntimeSettings()
    logging.basicConfig(level=settings.log_level)
    app.state.agent_builder = build_agent_builder(settings)
    yield


def get_agent_builder(request: Request) -> ReviewAgentBuilder:
    builder: ReviewAgentBuilder = request.app.state.agent_builder
    return builder


AgentBuilderDep = Annotated[ReviewAgentBuilder, Depends(get_agent_builder)]


async def review_to_response(agent: ReviewAgent, claim: ClaimUnderReview) -> ReviewResponse:
    try:
        outcome = await agent.review(claim)
    except Exception as exc:
        logger.exception("review of claim %s failed", claim.claim_id)
        usage = exc.usage if isinstance(exc, BedrockRunError) else TokenUsage()
        return ErrorResponse(usage=usage)
    match outcome:
        case ValidProposal():
            return ProposalResponse(
                proposal=outcome.proposal,
                retrieved_clauses=outcome.retrieved_clauses,
                model=outcome.model,
                usage=outcome.usage,
            )
        case NoValidProposal(detail=detail):
            return NoProposalResponse(detail=detail, usage=outcome.usage)


def create_runtime_app() -> FastAPI:
    app = FastAPI(title="Larkfield review agent", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "Healthy"}

    @app.post("/invocations")
    async def invoke(
        review_request: ReviewRequest,
        builder: AgentBuilderDep,
        session_id: Annotated[str | None, Header(alias=SESSION_ID_HEADER)] = None,
    ) -> ReviewResponse:
        claim = review_request.claim
        logger.info("claim %s: review started in session %s", claim.claim_id, session_id)
        history = PrefetchedHistory(
            review_request.possible_duplicates, review_request.training_claims
        )
        response = await review_to_response(builder.agent_for(history), claim)
        logger.info("claim %s: review finished with %s", claim.claim_id, response.outcome)
        return response

    return app


app = create_runtime_app()

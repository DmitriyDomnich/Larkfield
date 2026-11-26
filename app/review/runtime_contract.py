from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.core.metrics import TokenUsage
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim
from app.review.proposal import ReviewProposal


class ReviewRequest(BaseModel):
    claim: ClaimUnderReview
    possible_duplicates: list[PossibleClaimDuplicate]
    training_claims: list[TrainingClaim]


class ReviewResponse(BaseModel):
    usage: TokenUsage
    outcome: Literal["proposal", "no_proposal", "error"]


class ProposalResponse(ReviewResponse):
    outcome = "proposal"
    proposal: ReviewProposal
    retrieved_clauses: list[str]
    model: str


class NoProposalResponse(ReviewResponse):
    outcome = "no_proposal"
    detail: str


class ErrorResponse(ReviewResponse):
    """A Bedrock, KB or tool failure after spending `usage` tokens"""

    outcome = "error"


ReviewResponse = Annotated[
    ProposalResponse | NoProposalResponse | ErrorResponse, Field(discriminator="outcome")
]
REVIEW_RESPONSE: TypeAdapter[ReviewResponse] = TypeAdapter(ReviewResponse)

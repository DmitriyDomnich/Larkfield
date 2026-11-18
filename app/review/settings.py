from pydantic import Field

from app.core.config import Settings


class ReviewWorkerSettings(Settings):
    review_queue_url: str = Field(min_length=1)
    review_model_id: str = Field(min_length=1)
    policy_kb_id: str = Field(min_length=1)

    review_max_receives: int = 3
    review_max_turns: int = 12
    review_max_proposal_attempts: int = 3


class ReviewToolsSettings(Settings):
    policy_kb_id: str = Field(min_length=1)

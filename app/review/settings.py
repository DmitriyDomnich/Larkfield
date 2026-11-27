from pydantic import Field

from app.core.config import Settings


class ReviewWorkerSettings(Settings):
    review_model_id: str = Field(min_length=1)
    policy_kb_id: str = Field(min_length=1)

    review_max_receives: int = 3
    review_max_turns: int = 12
    review_max_proposal_attempts: int = 3
    review_resend_interval_seconds: int = 300
    review_resend_after_seconds: int = 900


class ReviewToolsSettings(Settings):
    policy_kb_id: str = Field(min_length=1)

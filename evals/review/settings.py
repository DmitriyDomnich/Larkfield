from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ReviewEvalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aws_region: str = Field(min_length=1)
    review_model_id: str = Field(min_length=1)
    policy_kb_id: str = Field(min_length=1)

    review_max_turns: int = 12
    review_max_proposal_attempts: int = 3

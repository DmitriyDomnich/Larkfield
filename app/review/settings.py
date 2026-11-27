from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import Settings


class ReviewWorkerSettings(Settings):
    review_model_id: str = Field(min_length=1)
    policy_kb_id: str = Field(min_length=1)
    # if set: the agent runs on Bedrock AgentCore Runtime; empty: in this process
    review_agent_runtime_arn: str = ""

    review_max_receives: int = 3
    review_max_turns: int = 12
    review_max_proposal_attempts: int = 3
    review_resend_interval_seconds: int = 300
    review_resend_after_seconds: int = 900


class ReviewToolsSettings(Settings):
    policy_kb_id: str = Field(min_length=1)


class ReviewRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aws_region: str = Field(min_length=1)
    review_model_id: str = Field(min_length=1)
    policy_kb_id: str = Field(min_length=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    review_max_turns: int = 12
    review_max_proposal_attempts: int = 3

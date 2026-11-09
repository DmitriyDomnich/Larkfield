from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config

from app.extraction.settings import WorkerSettings
from evals.extraction.models import TokenUsage

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

DOCUMENT_USAGE: ContextVar[TokenUsage] = ContextVar("document_usage")


def _record_usage(parsed: dict[str, Any], **_: Any) -> None:
    usage = parsed.get("usage")
    meter = DOCUMENT_USAGE.get(None)
    if usage and meter is not None:
        meter.input_tokens += usage["inputTokens"]
        meter.output_tokens += usage["outputTokens"]
        meter.attempts += 1


def metered_client(settings: WorkerSettings) -> "BedrockRuntimeClient":
    # bedrock client whose Converse calls add their tokens to DOCUMENT_USAGE
    client = boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(read_timeout=120, retries={"max_attempts": 10, "mode": "adaptive"}),
    )
    client.meta.events.register("after-call.bedrock-runtime.Converse", _record_usage)
    return client

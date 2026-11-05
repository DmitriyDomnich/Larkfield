import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import boto3
from botocore.config import Config
from pydantic import ValidationError

from app.extraction.pages import PageImage
from app.extraction.prompts import (
    NO_TOOL_FEEDBACK,
    RECORD_EXPENSE,
    REPORT_UNREADABLE,
    SYSTEM_PROMPT,
    USER_INSTRUCTION,
    extraction_tools,
)
from app.extraction.schemas import ExtractedExpense
from app.extraction.settings import WorkerSettings

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

logger = logging.getLogger(__name__)

MAX_EXTRACTION_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 8000
MAX_REASON_CHARS = 300


@dataclass(frozen=True)
class ValidExtraction:
    expense: ExtractedExpense
    model: str


@dataclass(frozen=True)
class UnreadableDocument:
    """`reason` is for the employee."""

    reason: str


@dataclass(frozen=True)
class InvalidExtraction:
    """No valid ExtractedExpense after every attempt; `errors` is for the log."""

    errors: str


ExtractionOutcome = ValidExtraction | UnreadableDocument | InvalidExtraction


class ExpenseExtractor(Protocol):
    async def extract_expense(self, pages: Sequence[PageImage]) -> ExtractionOutcome: ...


class BedrockExtractor:
    def __init__(
        self, settings: WorkerSettings, client: "BedrockRuntimeClient | None" = None
    ) -> None:
        self._model = settings.bedrock_model_id
        self._client = client or boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(read_timeout=120, retries={"max_attempts": 3, "mode": "standard"}),
        )
        self._tools = extraction_tools()

    async def extract_expense(self, pages: Sequence[PageImage]) -> ExtractionOutcome:
        content: list[dict[str, Any]] = [
            {"image": {"format": page.format, "source": {"bytes": page.data}}} for page in pages
        ]
        content.append({"text": USER_INSTRUCTION})
        messages: list[Mapping[str, Any]] = [{"role": "user", "content": content}]

        errors = ""
        for attempt in range(1, MAX_EXTRACTION_ATTEMPTS + 1):
            response = await asyncio.to_thread(self._call_converse, messages)
            message = response["output"]["message"]
            usage = response["usage"]
            logger.info(
                "extraction attempt %d: stop=%s input_tokens=%d output_tokens=%d",
                attempt,
                response["stopReason"],
                usage["inputTokens"],
                usage["outputTokens"],
            )
            tool_uses = [block["toolUse"] for block in message["content"] if "toolUse" in block]

            if len(tool_uses) != 1:
                errors = NO_TOOL_FEEDBACK
                feedback: list[dict[str, Any]] = (
                    [_tool_error_result(tool_use["toolUseId"], errors) for tool_use in tool_uses]
                    if tool_uses
                    else [{"text": errors}]
                )
            else:
                used_tool = tool_uses[0]
                if used_tool["name"] == REPORT_UNREADABLE:
                    return UnreadableDocument(_clean_unreadable_reason(used_tool["input"]))
                if used_tool["name"] == RECORD_EXPENSE:
                    try:
                        return ValidExtraction(
                            ExtractedExpense.model_validate(used_tool["input"]), self._model
                        )
                    except ValidationError as exc:
                        errors = _describe_validation_errors(exc)
                else:
                    errors = NO_TOOL_FEEDBACK
                feedback = [_tool_error_result(used_tool["toolUseId"], errors)]

            logger.info("extraction attempt %d invalid: %s", attempt, errors)
            messages.append(message)
            messages.append({"role": "user", "content": feedback})
        return InvalidExtraction(errors)

    def _call_converse(self, messages: list[Mapping[str, Any]]) -> Any:
        return self._client.converse(
            modelId=self._model,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,  # type: ignore[arg-type]
            toolConfig={"tools": self._tools, "toolChoice": {"auto": {}}},  # type: ignore[typeddict-item]
            inferenceConfig={"maxTokens": MAX_OUTPUT_TOKENS},
        )


def _tool_error_result(tool_use_id: str, text: str) -> dict[str, Any]:
    return {
        "toolResult": {"toolUseId": tool_use_id, "content": [{"text": text}], "status": "error"}
    }


def _describe_validation_errors(exc: ValidationError) -> str:
    """The validation errors without the rejected values"""
    descriptions = []
    for error in exc.errors(include_url=False):
        field_path = ".".join(str(part) for part in error["loc"]) or "expense"
        descriptions.append(f"{field_path}: {error['msg']}")
    return "; ".join(descriptions)


def _clean_unreadable_reason(tool_input: Mapping[str, Any]) -> str:
    reason = str(tool_input.get("reason") or "")
    single_line = " ".join(reason.split())
    shortened = single_line[:MAX_REASON_CHARS]
    without_final_dot = shortened.rstrip(" .")
    return without_final_dot or "the document is not legible"

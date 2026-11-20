import json
import sys
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TextIO

NAMESPACE_PREFIX = "Larkfield"


class MetricStage(StrEnum):
    EXTRACTION = "extraction"
    REVIEW = "review"


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


class ClaimMetrics:
    def __init__(self, app_env: str, stream: TextIO | None = None) -> None:
        self.namespace = f"{NAMESPACE_PREFIX}/{app_env}"
        self._stream = stream

    def claim_failed(self, stage: MetricStage, claim_id: uuid.UUID) -> None:
        self._emit(stage, claim_id, {"ClaimsFailed": 1})

    def bedrock_tokens(self, stage: MetricStage, claim_id: uuid.UUID, usage: TokenUsage) -> None:
        self._emit(
            stage,
            claim_id,
            {"BedrockInputTokens": usage.input_tokens, "BedrockOutputTokens": usage.output_tokens},
        )

    def _emit(self, stage: MetricStage, claim_id: uuid.UUID, values: dict[str, int]) -> None:
        line = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self.namespace,
                        "Dimensions": [["Stage"]],
                        "Metrics": [{"Name": name, "Unit": "Count"} for name in values],
                    }
                ],
            },
            "Stage": stage.value,
            "claim_id": str(claim_id),
            **values,
        }
        stream = self._stream or sys.stdout
        stream.write(json.dumps(line) + "\n")
        stream.flush()

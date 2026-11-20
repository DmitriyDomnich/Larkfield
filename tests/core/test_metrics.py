import json
import uuid

import pytest

from app.core.metrics import ClaimMetrics, MetricStage, TokenUsage
from tests.core.fakes import RecordingMetrics

CLAIM_ID = uuid.UUID("6f1c2a52-0d43-4e5b-9a7e-1c8b2f3d4e5f")


def test_a_failed_claim_is_one_emf_line_with_the_stage_dimension() -> None:
    metrics = RecordingMetrics()

    metrics.claim_failed(MetricStage.EXTRACTION, CLAIM_ID)

    [line] = metrics.lines()
    [directive] = line["_aws"]["CloudWatchMetrics"]
    assert directive == {
        "Namespace": "Larkfield/test",
        "Dimensions": [["Stage"]],
        "Metrics": [{"Name": "ClaimsFailed", "Unit": "Count"}],
    }
    assert isinstance(line["_aws"]["Timestamp"], int)
    assert line["Stage"] == "extraction"
    assert line["ClaimsFailed"] == 1
    # a property, searchable in Logs Insights, not a dimension
    assert line["claim_id"] == str(CLAIM_ID)


def test_bedrock_tokens_are_two_metrics_in_one_line() -> None:
    metrics = RecordingMetrics()

    metrics.bedrock_tokens(MetricStage.REVIEW, CLAIM_ID, TokenUsage(4000, 600))

    [line] = metrics.lines()
    [directive] = line["_aws"]["CloudWatchMetrics"]
    assert directive["Metrics"] == [
        {"Name": "BedrockInputTokens", "Unit": "Count"},
        {"Name": "BedrockOutputTokens", "Unit": "Count"},
    ]
    assert (line["Stage"], line["BedrockInputTokens"], line["BedrockOutputTokens"]) == (
        "review",
        4000,
        600,
    )


@pytest.mark.parametrize("app_env", ["dev", "prod"])
def test_the_namespace_is_per_environment(app_env: str) -> None:
    assert ClaimMetrics(app_env).namespace == f"Larkfield/{app_env}"


def test_lines_go_to_stdout_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    ClaimMetrics("dev").claim_failed(MetricStage.REVIEW, CLAIM_ID)

    [line] = capsys.readouterr().out.splitlines()
    assert json.loads(line)["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Larkfield/dev"


def test_token_usage_adds_up() -> None:
    assert TokenUsage(10, 5) + TokenUsage(3, 2) == TokenUsage(13, 7)

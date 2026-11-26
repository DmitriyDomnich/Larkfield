import pytest

from app.review.agent import StrandsReviewAgent
from app.review.agentcore import AgentCoreClient
from app.review.settings import ReviewWorkerSettings
from app.review.worker import build_review_agent
from tests.review.fakes import RUNTIME_ARN, FakeHistory


def test_a_runtime_arn_sends_the_review_to_agentcore() -> None:
    settings = ReviewWorkerSettings(review_agent_runtime_arn=RUNTIME_ARN)

    assert isinstance(build_review_agent(settings, FakeHistory()), AgentCoreClient)


def test_no_runtime_arn_keeps_the_agent_in_process() -> None:
    settings = ReviewWorkerSettings(review_agent_runtime_arn="")

    assert isinstance(build_review_agent(settings, FakeHistory()), StrandsReviewAgent)


def test_the_runtime_arn_is_empty_unless_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVIEW_AGENT_RUNTIME_ARN", raising=False)

    assert ReviewWorkerSettings(_env_file=None).review_agent_runtime_arn == ""

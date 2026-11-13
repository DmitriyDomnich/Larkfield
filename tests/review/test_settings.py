import pytest
from pydantic import ValidationError

from app.review.settings import ReviewWorkerSettings


@pytest.mark.parametrize("name", ["REVIEW_QUEUE_URL", "REVIEW_MODEL_ID", "POLICY_KB_ID"])
def test_review_worker_refuses_an_empty_queue_model_or_kb(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    # docker compose passes an unset variable as an empty string
    monkeypatch.setenv(name, "")

    with pytest.raises(ValidationError, match=name.lower()):
        ReviewWorkerSettings(_env_file=None)


def test_review_worker_limits_default() -> None:
    settings = ReviewWorkerSettings()

    assert settings.review_max_receives == 3
    assert settings.review_max_turns == 12
    assert settings.review_max_proposal_attempts == 3

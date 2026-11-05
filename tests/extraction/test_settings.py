import pytest
from pydantic import ValidationError

from app.extraction.settings import WorkerSettings


@pytest.mark.parametrize("name", ["EXTRACTION_QUEUE_URL", "BEDROCK_MODEL_ID"])
def test_worker_refuses_an_empty_queue_or_model(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    # docker compose passes an unset variable as an empty string
    monkeypatch.setenv(name, "")

    with pytest.raises(ValidationError, match=name.lower()):
        WorkerSettings(_env_file=None)

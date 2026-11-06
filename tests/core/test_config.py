import pytest
from pydantic import ValidationError

from app.core.config import Settings, WorkerSettings


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/larkfield")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.database_url.hosts()[0]["host"] == "db.example"
    assert settings.app_env == "dev"
    assert settings.log_level == "DEBUG"


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_api_settings_do_not_need_the_worker_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTRACTION_QUEUE_URL", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    Settings(_env_file=None)


@pytest.mark.parametrize("name", ["EXTRACTION_QUEUE_URL", "BEDROCK_MODEL_ID"])
def test_worker_refuses_an_empty_queue_or_model(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    # docker compose passes an unset variable as an empty string
    monkeypatch.setenv(name, "")

    with pytest.raises(ValidationError, match=name.lower()):
        WorkerSettings(_env_file=None)

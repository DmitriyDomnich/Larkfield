"""The browser app calls the API from another origin; only the configured origins may."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ALLOWED = "http://localhost:3000"


@pytest.fixture
def api(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings.frontend_origins = [ALLOWED]
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    return TestClient(create_app())


def preflight(api: TestClient, origin: str) -> dict[str, str]:
    response = api.options(
        "/claims",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    return dict(response.headers)


def test_preflight_from_the_frontend_origin_is_allowed(api: TestClient) -> None:
    headers = preflight(api, ALLOWED)

    assert headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in headers["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in headers


def test_preflight_from_another_origin_is_refused(api: TestClient) -> None:
    assert "access-control-allow-origin" not in preflight(api, "https://evil.example")


def test_no_origin_is_allowed_by_default() -> None:
    assert Settings(_env_file=None).frontend_origins == []

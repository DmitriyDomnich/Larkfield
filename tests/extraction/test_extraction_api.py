"""GET /claims/{id}/extraction without a database: roles and the OpenAPI document."""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_token_verifier
from app.core.config import Settings
from tests.claims.fakes import auth
from tests.tokens import make_verifier

PATH = "/claims/00000000-0000-0000-0000-000000000000/extraction"


@pytest.fixture
def api(client: TestClient, settings: Settings) -> TestClient:
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_token_verifier] = lambda: make_verifier(settings)
    return client


def test_extraction_needs_a_token(api: TestClient) -> None:
    assert api.get(PATH).status_code == 401


def test_extraction_is_closed_to_admins(api: TestClient, settings: Settings) -> None:
    response = api.get(PATH, headers=auth(settings, sub="admin-1", role="admin"))

    assert response.status_code == 403


def test_openapi_documents_the_extraction_endpoint(api: TestClient) -> None:
    operation = api.get("/openapi.json").json()["paths"]["/claims/{claim_id}/extraction"]["get"]

    assert operation["summary"]
    assert {"200", "401", "403", "404"} <= set(operation["responses"])
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ExtractionRead"
    }

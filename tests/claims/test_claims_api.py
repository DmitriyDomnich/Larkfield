"""Claims endpoints without a database: request validation, roles and the OpenAPI document."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_token_verifier
from app.claims.storage import get_storage
from app.core.config import Settings
from tests.claims.fakes import FakeStorage, auth, claim_body
from tests.tokens import make_verifier


@pytest.fixture
def api(client: TestClient, settings: Settings) -> TestClient:
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_token_verifier] = lambda: make_verifier(settings)
    overrides[get_storage] = FakeStorage
    return client


def with_changes(**changes: Any) -> dict[str, Any]:
    body = claim_body()
    file = {**body["file"], **changes.pop("file", {})}  # type: ignore[dict-item]
    return {**body, **changes, "file": file}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(with_changes(purpose="x" * 9), id="purpose-too-short"),
        pytest.param(with_changes(purpose="x" * 501), id="purpose-too-long"),
        pytest.param(with_changes(preapproval_ref="PA-26-114"), id="bad-preapproval-ref"),
        pytest.param(with_changes(attendees=[{"name": "A. Novak"}]), id="attendee-no-company"),
        pytest.param(with_changes(status="approved"), id="client-sets-status"),
        pytest.param(with_changes(submitted_at="2026-01-01T00:00:00Z"), id="client-sets-date"),
        pytest.param(
            with_changes(file={"content_type": "application/x-msdownload"}), id="executable"
        ),
        pytest.param(with_changes(file={"content_type": "image/gif"}), id="gif"),
        pytest.param(with_changes(file={"size_bytes": 0}), id="empty-file"),
        pytest.param(with_changes(file={"size_bytes": 10 * 1024 * 1024 + 1}), id="over-10-mb"),
    ],
)
def test_invalid_claim_is_422(api: TestClient, settings: Settings, body: dict[str, Any]) -> None:
    response = api.post("/claims", json=body, headers=auth(settings))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "status=bogus"], ids=lambda q: q
)
def test_invalid_list_query_is_422(api: TestClient, settings: Settings, query: str) -> None:
    assert api.get(f"/claims?{query}", headers=auth(settings)).status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/claims"),
        ("GET", "/claims"),
        ("GET", "/claims/00000000-0000-0000-0000-000000000000"),
        ("GET", "/claims/00000000-0000-0000-0000-000000000000/file"),
        ("POST", "/claims/00000000-0000-0000-0000-000000000000/upload-complete"),
    ],
)
def test_claims_need_a_token_and_are_closed_to_admins(
    api: TestClient, settings: Settings, method: str, path: str
) -> None:
    body = claim_body() if method == "POST" else None

    assert api.request(method, path, json=body).status_code == 401
    admin = auth(settings, sub="admin-1", role="admin")
    assert api.request(method, path, json=body, headers=admin).status_code == 403


def test_openapi_documents_every_claims_endpoint(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]

    expected = {
        ("/claims", "post"): {"201", "401", "403", "422"},
        ("/claims", "get"): {"200", "401", "403", "422"},
        ("/claims/{claim_id}", "get"): {"200", "401", "403", "404"},
        ("/claims/{claim_id}/file", "get"): {"200", "401", "403", "404"},
        ("/claims/{claim_id}/upload-complete", "post"): {"200", "401", "403", "404", "409", "422"},
    }
    for (path, method), codes in expected.items():
        operation = paths[path][method]
        assert operation["summary"]
        assert codes <= set(operation["responses"]), (path, method)

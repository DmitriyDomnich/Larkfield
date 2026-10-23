"""Integration tests: need a real PostgreSQL at DATABASE_URL (CI service / docker compose)."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_health_ok_against_real_database(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}

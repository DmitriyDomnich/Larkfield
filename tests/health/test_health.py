import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.db import get_engine
from app.health.service import database_is_reachable


def _override_engine(client: TestClient, engine: AsyncEngine) -> None:
    client.app.dependency_overrides[get_engine] = lambda: engine  # type: ignore[attr-defined]


def _healthy_engine() -> MagicMock:
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value.__aenter__.return_value = AsyncMock()
    return engine


def _failing_engine() -> MagicMock:
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.side_effect = OperationalError(
        "SELECT 1", {}, Exception("password=hunter2 host=db")
    )
    return engine


def _hanging_engine() -> MagicMock:
    async def never_returns(*_: object) -> None:
        await asyncio.sleep(60)

    engine = _healthy_engine()
    engine.connect.return_value.__aenter__.return_value.execute.side_effect = never_returns
    return engine


def test_health_ok_when_database_reachable(client: TestClient) -> None:
    _override_engine(client, _healthy_engine())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    _override_engine(client, _failing_engine())

    response = client.get("/health")

    assert response.status_code == 503
    # Exact body: the driver error (with its password) must not leak into the response.
    assert response.json() == {"status": "error", "database": "unreachable"}
    assert "Database health check failed" in caplog.text


async def test_hanging_database_times_out(settings: Settings) -> None:
    settings.db_connect_timeout = 1

    async with asyncio.timeout(3):  # fails the test if our own timeout doesn't fire
        assert await database_is_reachable(_hanging_engine(), settings) is False

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

if "DATABASE_URL" not in os.environ and not Path(".env").exists():
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/larkfield_test"

from app.core.config import Settings, get_settings  # needs DATABASE_URL set first
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    # A fresh copy
    return get_settings().model_copy()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

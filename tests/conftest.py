import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

if "DATABASE_URL" not in os.environ and not Path(".env").exists():
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/larkfield_test"

from app.core.config import Settings, get_settings  # needs DATABASE_URL set first
from app.core.db import build_engine
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


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Bring the database at DATABASE_URL to the latest migration, once per test run."""
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False  # keep pytest's log capture working
    command.upgrade(config, "head")


@pytest.fixture
async def db_session(migrated_database: None, settings: Settings) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after the test, so no test sees
    another test's data. Commits inside the test only release a savepoint."""
    engine = build_engine(settings)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        yield session
        await session.close()
        await transaction.rollback()
    await engine.dispose()

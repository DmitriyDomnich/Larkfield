"""Integration tests: need a real PostgreSQL at DATABASE_URL (CI service / docker compose)."""

from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import make_url

from app.core.config import Settings

pytestmark = pytest.mark.integration


def _plain_url(url: str) -> str:
    """SQLAlchemy URL -> libpq URL that psycopg.connect accepts."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def scratch_config(settings: Settings) -> Iterator[Config]:
    """Alembic config pointed at a throwaway database, so downgrading never touches the one
    the other tests (or the developer) use."""
    base_url = make_url(str(settings.database_url))
    name = f"{base_url.database}_migrations"
    scratch_url = base_url.set(database=name).render_as_string(hide_password=False)

    with psycopg.connect(_plain_url(str(settings.database_url)), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')

    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False
    config.attributes["settings"] = settings.model_copy(update={"database_url": scratch_url})
    yield config

    with psycopg.connect(_plain_url(str(settings.database_url)), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_every_migration_upgrades_and_downgrades_cleanly(scratch_config: Config) -> None:
    revisions = list(ScriptDirectory.from_config(scratch_config).walk_revisions())
    revisions.reverse()  # walk_revisions goes head -> base

    # Stairway: each revision goes up, back down one step and up again.
    for revision in revisions:
        command.upgrade(scratch_config, revision.revision)
        command.downgrade(scratch_config, "-1")
        command.upgrade(scratch_config, revision.revision)

    command.downgrade(scratch_config, "base")

    # Nothing may be left behind but Alembic's own version table.
    url = _plain_url(str(scratch_config.attributes["settings"].database_url))
    with psycopg.connect(url) as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        functions = conn.execute(
            "SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace"
        ).fetchall()
    assert tables == [("alembic_version",)]
    assert functions == []

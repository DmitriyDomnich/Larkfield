"""Integration tests: need a real PostgreSQL at DATABASE_URL (CI service / docker compose)."""

from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import Settings
from tests.db import create_database, derived_database_url, drop_database

pytestmark = pytest.mark.integration


@pytest.fixture
def scratch_config(settings: Settings) -> Iterator[Config]:
    """Alembic config pointed at its own throwaway database, so downgrading never touches the
    test database the other tests use."""
    url = derived_database_url("migrations")
    create_database(url)
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False
    config.attributes["settings"] = settings.model_copy(update={"database_url": url})
    yield config
    drop_database(url)


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
    with psycopg.connect(str(scratch_config.attributes["settings"].database_url)) as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        functions = conn.execute(
            "SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace"
        ).fetchall()
    assert tables == [("alembic_version",)]
    assert functions == []

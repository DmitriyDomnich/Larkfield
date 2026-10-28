"""Throwaway databases for tests, so a test run never touches the developer's database.

Names are derived from the configured DATABASE_URL (`larkfield` -> `larkfield_test`)
"""

import psycopg
from psycopg import sql
from sqlalchemy import make_url

from app.core.config import Settings

_configured = make_url(str(Settings().database_url))


def derived_database_url(suffix: str) -> str:
    """URL of `<configured name>_<suffix>` on the same server."""
    url = _configured.set(database=f"{_configured.database}_{suffix}")
    return url.render_as_string(hide_password=False)


def create_database(url: str) -> None:
    """Create the database `url` names, dropping a leftover one from a crashed run first."""
    drop_database(url)
    with _admin() as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_name(url))))


def drop_database(url: str) -> None:
    with _admin() as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(_name(url)))
        )


def _admin() -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(_configured.render_as_string(hide_password=False), autocommit=True)


def _name(url: str) -> str:
    name = make_url(url).database
    assert name, f"no database name in {make_url(url)!r}"
    return name

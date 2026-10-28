"""Alembic environment. The database URL comes from Settings (DATABASE_URL), not from alembic.ini.

Tests can run migrations against another database by passing their own Settings:
`config.attributes["settings"] = settings`.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic_utils.replaceable_entity import register_entities
from sqlalchemy.engine import Connection

import app.claims.models
import app.claims.triggers
import app.extraction.models
import app.review.models  # registers every table on Base.metadata
import app.review.triggers
from app.core.config import Settings, get_settings
from app.core.db import build_engine
from app.core.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# list PG functions and triggers
DB_ENTITIES = app.claims.triggers.ENTITIES + app.review.triggers.ENTITIES
register_entities(DB_ENTITIES)


def _settings() -> Settings:
    settings: Settings | None = config.attributes.get("settings")
    return settings or get_settings()


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    context.configure(
        url=build_engine(_settings()).url,  # builds the URL only; does not connect
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = build_engine(_settings())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())

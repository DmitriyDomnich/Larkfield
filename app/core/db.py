"""Database engine and session wiring (async SQLAlchemy on psycopg 3)."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    # SQLAlchemy needs the psycopg 3 driver named explicitly in the URL.
    url = str(settings.database_url).replace("postgresql://", "postgresql+psycopg://", 1)
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
        },
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


async def get_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncGenerator[AsyncSession]:
    async with factory() as session:
        yield session

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import configure_mappers

from app.core.config import get_settings
from app.core.db import build_engine, build_session_factory
from app.health.router import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_mappers()
    engine = build_engine(get_settings())
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI app; each feature package contributes a router."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(title="Larkfield", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()

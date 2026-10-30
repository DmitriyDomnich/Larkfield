import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import configure_mappers

from app.auth.cognito import CognitoUserDirectory
from app.auth.tokens import TokenVerifier
from app.claims.router import router as claims_router
from app.claims.router import transition_refused
from app.claims.service import ConcurrentTransitionError, InvalidTransitionError
from app.claims.storage import S3ObjectStorage
from app.core.config import get_settings
from app.core.db import build_engine, build_session_factory
from app.health.router import router as health_router
from app.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_mappers()
    settings = get_settings()
    engine = build_engine(settings)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.token_verifier = TokenVerifier(settings)
    app.state.user_directory = CognitoUserDirectory(settings)
    app.state.storage = S3ObjectStorage(settings)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI app; each feature package contributes a router."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(
        title="Larkfield",
        version="0.1.0",
        lifespan=lifespan,
        exception_handlers={
            InvalidTransitionError: transition_refused,
            ConcurrentTransitionError: transition_refused,
        },
    )
    app.include_router(health_router)
    app.include_router(users_router)
    app.include_router(claims_router)
    return app


app = create_app()

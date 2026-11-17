import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.claims.models import Claim
from app.core.config import Settings
from app.core.db import build_engine
from app.review.mcp_server import build_readonly_sessions

pytestmark = pytest.mark.integration


async def test_the_server_sessions_read_but_never_write(settings: Settings) -> None:
    engine = build_engine(settings)
    sessions = build_readonly_sessions(engine)
    try:
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Claim)) is not None

            with pytest.raises(DBAPIError, match="read-only transaction"):
                await session.execute(update(Claim).where(Claim.id.is_(None)).values(purpose="x"))
    finally:
        await engine.dispose()

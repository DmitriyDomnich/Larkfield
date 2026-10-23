import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def database_is_reachable(engine: AsyncEngine, settings: Settings) -> bool:
    """Run `SELECT 1`; any error or timeout means unreachable."""
    try:
        async with asyncio.timeout(settings.db_connect_timeout), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, TimeoutError):
        logger.warning("Database health check failed", exc_info=True)
        return False
    return True

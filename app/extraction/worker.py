import asyncio
import logging
import signal
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.storage import ObjectStorage, S3ObjectStorage
from app.core.db import build_engine, build_session_factory
from app.extraction.extractor import BedrockExtractor, ExpenseExtractor
from app.extraction.queue import SqsUploadQueue, UploadMessage, UploadQueue
from app.extraction.service import process_upload
from app.extraction.settings import WorkerSettings

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class ExtractionWorker:
    def __init__(
        self,
        settings: WorkerSettings,
        queue: UploadQueue,
        sessions: SessionFactory,
        storage: ObjectStorage,
        extractor: ExpenseExtractor,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._sessions = sessions
        self._storage = storage
        self._extractor = extractor

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("extraction worker started")
        while not stop.is_set():
            try:
                messages = await self._queue.receive_messages()
            except Exception:
                logger.exception("receiving from the queue failed")
                await asyncio.sleep(5)
                continue
            for message in messages:
                await self.handle_message(message)
        logger.info("extraction worker stopped")

    async def handle_message(self, message: UploadMessage) -> None:
        try:
            for uploaded in message.objects:
                async with self._sessions() as session:
                    await process_upload(
                        session,
                        self._storage,
                        self._extractor,
                        uploaded,
                        today=datetime.now(UTC).date(),
                        receive_count=message.receive_count,
                        max_receives=self._settings.extraction_max_receives,
                        max_pages=self._settings.extraction_max_pages,
                    )
        except Exception:
            logger.exception(
                "processing an upload failed (delivery %d of %d)",
                message.receive_count,
                self._settings.extraction_max_receives,
            )
            return
        await self._queue.delete_message(message.receipt_handle)


async def run_worker() -> None:
    settings = WorkerSettings()
    logging.basicConfig(level=settings.log_level)
    engine = build_engine(settings)
    worker = ExtractionWorker(
        settings,
        SqsUploadQueue(settings),
        build_session_factory(engine),
        S3ObjectStorage(settings),
        BedrockExtractor(settings),
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    # ECS and `docker stop` send SIGTERM; finish the current message, then exit
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await worker.run(stop)
    finally:
        await engine.dispose()

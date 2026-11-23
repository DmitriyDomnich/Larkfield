import asyncio
import logging
import signal
from datetime import UTC, datetime

from app.claims.status import ClaimStatus
from app.claims.storage import ObjectStorage, S3ObjectStorage
from app.core.db import SessionFactory, build_engine, build_session_factory
from app.core.metrics import ClaimMetrics, MetricStage
from app.extraction.extractor import BedrockExtractor, ExpenseExtractor
from app.extraction.queue import SqsUploadQueue, UploadMessage, UploadQueue
from app.extraction.service import process_upload
from app.extraction.settings import WorkerSettings
from app.notifications.queue import (
    NotificationService,
    SqsNotificationService,
    notify_claim_failed,
)
from app.review.queue import ReviewRequests, SqsReviewQueue

logger = logging.getLogger(__name__)


class ExtractionWorker:
    def __init__(
        self,
        settings: WorkerSettings,
        queue: UploadQueue,
        sessions: SessionFactory,
        storage: ObjectStorage,
        extractor: ExpenseExtractor,
        reviews: ReviewRequests,
        notification_service: NotificationService,
        metrics: ClaimMetrics,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._sessions = sessions
        self._storage = storage
        self._extractor = extractor
        self._reviews = reviews
        self._notification_service = notification_service
        self._metrics = metrics

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
                    finished_claim = await process_upload(
                        session,
                        self._storage,
                        self._extractor,
                        self._metrics,
                        uploaded,
                        today=datetime.now(UTC).date(),
                        receive_count=message.receive_count,
                        max_receives=self._settings.extraction_max_receives,
                        max_pages=self._settings.extraction_max_pages,
                    )
                if finished_claim is None:
                    continue
                if finished_claim.status is ClaimStatus.EXTRACTED:
                    # if this fails -> the redelivery requests it again
                    await self._reviews.request_review(finished_claim.claim_id)
                else:
                    await self._metrics.claim_failed(
                        MetricStage.EXTRACTION, finished_claim.claim_id
                    )
                    await notify_claim_failed(
                        self._sessions, self._notification_service, finished_claim.claim_id
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
        SqsReviewQueue(settings),
        SqsNotificationService(settings),
        ClaimMetrics(settings.app_env),
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

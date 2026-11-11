import asyncio
import logging
import signal

from botocore.config import Config
from strands.models.bedrock import BedrockModel

from app.core.db import SessionFactory, build_engine, build_session_factory
from app.review.agent import ReviewAgent, StrandsReviewAgent
from app.review.claims_history import DatabaseClaimsHistory
from app.review.policy import BedrockPolicyRetriever
from app.review.queue import ReviewMessage, ReviewQueue, SqsReviewQueue
from app.review.service import review_claim
from app.review.settings import ReviewWorkerSettings

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 4000


class ReviewWorker:
    def __init__(
        self,
        settings: ReviewWorkerSettings,
        queue: ReviewQueue,
        sessions: SessionFactory,
        agent: ReviewAgent,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._sessions = sessions
        self._agent = agent

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("review worker started")
        while not stop.is_set():
            try:
                messages = await self._queue.receive_messages()
            except Exception:
                logger.exception("receiving from the queue failed")
                await asyncio.sleep(5)
                continue
            for message in messages:
                await self.handle_message(message)
        logger.info("review worker stopped")

    async def handle_message(self, message: ReviewMessage) -> None:
        if message.claim_id is not None:
            try:
                await review_claim(
                    self._sessions,
                    self._agent,
                    message.claim_id,
                    receive_count=message.receive_count,
                    max_receives=self._settings.review_max_receives,
                )
            except Exception:
                logger.exception(
                    "reviewing claim %s failed (delivery %d of %d)",
                    message.claim_id,
                    message.receive_count,
                    self._settings.review_max_receives,
                )
                return
        await self._queue.delete_message(message.receipt_handle)


async def run_worker() -> None:
    settings = ReviewWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    engine = build_engine(settings)
    sessions = build_session_factory(engine)
    try:
        agent = StrandsReviewAgent(
            BedrockModel(
                model_id=settings.review_model_id,
                region_name=settings.aws_region,
                boto_client_config=Config(read_timeout=120),
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0,
            ),
            settings.review_model_id,
            BedrockPolicyRetriever(settings.policy_kb_id, settings.aws_region),
            DatabaseClaimsHistory(sessions),
            max_turns=settings.review_max_turns,
            max_proposal_attempts=settings.review_max_proposal_attempts,
        )
        worker = ReviewWorker(
            settings,
            SqsReviewQueue(settings),
            sessions,
            agent,
        )
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        # ECS and `docker stop` send SIGTERM; finish the current claim, then exit
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await worker.run(stop)
    finally:
        await engine.dispose()

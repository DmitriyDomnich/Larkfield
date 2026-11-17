import asyncio
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol

import boto3
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import select

from app.claims.models import Claim
from app.claims.status import ClaimStatus
from app.core.db import SessionFactory

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient

logger = logging.getLogger(__name__)

NotifiedStatus = Literal[
    ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.NEEDS_INFO, ClaimStatus.FAILED
]


class ClaimNotification(BaseModel):
    claim_id: uuid.UUID
    employee_sub: str
    status: NotifiedStatus
    purpose: str
    submitted_at: datetime
    comment: str | None = None
    failure_reason: str | None = None


def build_notification(
    claim: Claim, status: NotifiedStatus, comment: str | None = None
) -> ClaimNotification:
    return ClaimNotification(
        claim_id=claim.id,
        employee_sub=claim.employee_sub,
        status=status,
        purpose=claim.purpose,
        submitted_at=claim.submitted_at,
        comment=comment,
        failure_reason=claim.failure_reason if status is ClaimStatus.FAILED else None,
    )


class NotificationQueueSettings(Protocol):
    notification_queue_url: str
    aws_region: str


class NotificationService(Protocol):
    async def notify(self, notification: ClaimNotification) -> None: ...


class SqsNotificationService:
    def __init__(
        self, settings: NotificationQueueSettings, client: "SQSClient | None" = None
    ) -> None:
        self._url = settings.notification_queue_url
        self._client = client or boto3.client("sqs", region_name=settings.aws_region)

    async def notify(self, notification: ClaimNotification) -> None:
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=self._url,
            MessageBody=notification.model_dump_json(),
        )


async def send_notification(
    notification_service: NotificationService, notification: ClaimNotification
) -> None:
    try:
        await notification_service.notify(notification)
    except Exception:
        logger.exception(
            "the %s notification for claim %s could not be queued",
            notification.status,
            notification.claim_id,
        )

async def notify_claim_failed(
    sessions: SessionFactory, notification_service: NotificationService, claim_id: uuid.UUID
) -> None:
    async with sessions() as session:
        claim = await session.scalar(
            select(Claim).where(Claim.id == claim_id).execution_options(populate_existing=True)
        )
    if claim is None or claim.status is not ClaimStatus.FAILED:
        return
    await send_notification(notification_service, build_notification(claim, ClaimStatus.FAILED))


def get_notification_service(request: Request) -> NotificationService:
    notification_service: NotificationService = request.app.state.notification_service
    return notification_service

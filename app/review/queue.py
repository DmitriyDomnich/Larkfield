import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import boto3

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient

logger = logging.getLogger(__name__)

RECEIVE_WAIT_SECONDS = 20


@dataclass(frozen=True)
class ReviewMessage:
    receipt_handle: str
    claim_id: uuid.UUID | None
    receive_count: int


class ReviewQueueSettings(Protocol):
    review_queue_url: str
    aws_region: str


class ReviewRequests(Protocol):
    async def request_review(self, claim_id: uuid.UUID) -> None: ...


class ReviewQueue(Protocol):
    async def receive_messages(self) -> list[ReviewMessage]:
        """Wait up to RECEIVE_WAIT_SECONDS for a message"""
        ...

    async def delete_message(self, receipt_handle: str) -> None: ...


class SqsReviewQueue:
    def __init__(self, settings: ReviewQueueSettings, client: "SQSClient | None" = None) -> None:
        self._url = settings.review_queue_url
        self._client = client or boto3.client("sqs", region_name=settings.aws_region)

    async def request_review(self, claim_id: uuid.UUID) -> None:
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=self._url,
            MessageBody=json.dumps({"claim_id": str(claim_id)}),
        )

    async def receive_messages(self) -> list[ReviewMessage]:
        response = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=self._url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=RECEIVE_WAIT_SECONDS,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        return [
            ReviewMessage(
                receipt_handle=message["ReceiptHandle"],
                claim_id=requested_claim(message["Body"]),
                receive_count=int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1)),
            )
            for message in response.get("Messages", [])
        ]

    async def delete_message(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self._client.delete_message, QueueUrl=self._url, ReceiptHandle=receipt_handle
        )


def requested_claim(body: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(json.loads(body)["claim_id"])
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.warning("ignoring a message that is not a review request")
        return None

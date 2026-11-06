import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import unquote_plus

import boto3

from app.core.config import WorkerSettings

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient

logger = logging.getLogger(__name__)

RECEIVE_WAIT_SECONDS = 20


@dataclass(frozen=True)
class UploadedObject:
    key: str
    version_id: str | None


@dataclass(frozen=True)
class UploadMessage:
    receipt_handle: str
    objects: list[UploadedObject]
    receive_count: int


class UploadQueue(Protocol):
    async def receive_messages(self) -> list[UploadMessage]:
        """Wait up to RECEIVE_WAIT_SECONDS for a message"""
        ...

    async def delete_message(self, receipt_handle: str) -> None: ...


class SqsUploadQueue:
    def __init__(self, settings: WorkerSettings, client: "SQSClient | None" = None) -> None:
        self._url = settings.extraction_queue_url
        self._client = client or boto3.client("sqs", region_name=settings.aws_region)

    async def receive_messages(self) -> list[UploadMessage]:
        response = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=self._url,
            # one message at a time
            MaxNumberOfMessages=1,
            WaitTimeSeconds=RECEIVE_WAIT_SECONDS,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        return [
            UploadMessage(
                receipt_handle=message["ReceiptHandle"],
                objects=created_objects(message["Body"]),
                receive_count=int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1)),
            )
            for message in response.get("Messages", [])
        ]

    async def delete_message(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self._client.delete_message, QueueUrl=self._url, ReceiptHandle=receipt_handle
        )


def created_objects(body: str) -> list[UploadedObject]:
    try:
        event: Any = json.loads(body)
        records = event.get("Records", []) if isinstance(event, dict) else []
        return [
            UploadedObject(
                key=unquote_plus(record["s3"]["object"]["key"]),
                version_id=record["s3"]["object"].get("versionId"),
            )
            for record in records
            if str(record.get("eventName", "")).startswith("ObjectCreated:")
        ]
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.warning("ignoring a message that is not an S3 event")
        return []

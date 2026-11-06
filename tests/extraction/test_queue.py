import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

from app.core.config import WorkerSettings
from app.extraction.queue import (
    RECEIVE_WAIT_SECONDS,
    SqsUploadQueue,
    UploadedObject,
    UploadMessage,
    created_objects,
)


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")


@pytest.fixture
def worker_settings() -> WorkerSettings:
    return WorkerSettings()


@pytest.fixture
def stubbed(worker_settings: WorkerSettings) -> Iterator[tuple[SqsUploadQueue, Stubber]]:
    client = boto3.client("sqs", region_name=worker_settings.aws_region)
    with Stubber(client) as stubber:
        yield SqsUploadQueue(worker_settings, client=client), stubber
        stubber.assert_no_pending_responses()


def s3_event(*keys: str, event_name: str = "ObjectCreated:Post", version_id: str = "v1") -> str:
    return json.dumps(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": event_name,
                    "s3": {
                        "bucket": {"name": "documents"},
                        "object": {"key": key, "size": 1, "versionId": version_id},
                    },
                }
                for key in keys
            ]
        }
    )


async def test_receive_long_polls_for_one_message_with_its_delivery_count(
    stubbed: tuple[SqsUploadQueue, Stubber], worker_settings: WorkerSettings
) -> None:
    queue, stubber = stubbed
    message: dict[str, Any] = {
        "ReceiptHandle": "handle-1",
        "Body": s3_event("claims/c/d"),
        "Attributes": {"ApproximateReceiveCount": "2"},
    }
    stubber.add_response(
        "receive_message",
        {"Messages": [message]},
        {
            "QueueUrl": worker_settings.extraction_queue_url,
            "MaxNumberOfMessages": 1,
            "WaitTimeSeconds": RECEIVE_WAIT_SECONDS,
            "MessageSystemAttributeNames": ["ApproximateReceiveCount"],
        },
    )

    assert await queue.receive_messages() == [
        UploadMessage("handle-1", [UploadedObject("claims/c/d", "v1")], 2)
    ]


async def test_receive_returns_nothing_when_the_wait_ends_empty(
    stubbed: tuple[SqsUploadQueue, Stubber],
) -> None:
    queue, stubber = stubbed
    stubber.add_response("receive_message", {})

    assert await queue.receive_messages() == []


async def test_delete(
    stubbed: tuple[SqsUploadQueue, Stubber], worker_settings: WorkerSettings
) -> None:
    queue, stubber = stubbed
    stubber.add_response(
        "delete_message",
        {},
        {"QueueUrl": worker_settings.extraction_queue_url, "ReceiptHandle": "handle-1"},
    )

    await queue.delete_message("handle-1")


def test_keys_are_url_decoded() -> None:
    assert [obj.key for obj in created_objects(s3_event("claims/a+b/c%2Bd"))] == ["claims/a b/c+d"]


def test_each_object_carries_the_version_its_upload_created() -> None:
    version = "3HL4kqtJlcpXroDTDmJ+rmSpXd3dIbrH"

    assert created_objects(s3_event("claims/c/d", version_id=version)) == [
        UploadedObject("claims/c/d", version)
    ]


def test_an_unversioned_bucket_gives_no_version() -> None:
    body = json.loads(s3_event("claims/c/d"))
    del body["Records"][0]["s3"]["object"]["versionId"]

    assert created_objects(json.dumps(body)) == [UploadedObject("claims/c/d", None)]


def test_only_created_objects_count() -> None:
    body = json.loads(s3_event("claims/c/d"))
    body["Records"] += json.loads(s3_event("claims/c/e", event_name="ObjectRemoved:Delete"))[
        "Records"
    ]

    assert [obj.key for obj in created_objects(json.dumps(body))] == ["claims/c/d"]


@pytest.mark.parametrize(
    "body",
    [
        json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent", "Bucket": "documents"}),
        "not json",
        json.dumps(["a", "list"]),
        json.dumps({"Records": [{"eventName": "ObjectCreated:Put"}]}),
    ],
    ids=["s3-test-event", "not-json", "not-an-object", "record-without-s3"],
)
def test_messages_that_are_not_upload_events_have_no_keys(body: str) -> None:
    assert created_objects(body) == []

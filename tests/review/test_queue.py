import json
import uuid
from collections.abc import Iterator

import boto3
import pytest
from botocore.stub import Stubber

from app.extraction.settings import WorkerSettings
from app.review.queue import RECEIVE_WAIT_SECONDS, ReviewMessage, SqsReviewQueue, requested_claim
from app.review.settings import ReviewWorkerSettings

QUEUE_URL = ReviewWorkerSettings().review_queue_url


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")


@pytest.fixture
def stubbed() -> Iterator[tuple[SqsReviewQueue, Stubber]]:
    settings = ReviewWorkerSettings()
    client = boto3.client("sqs", region_name=settings.aws_region)
    with Stubber(client) as stubber:
        yield SqsReviewQueue(settings, client=client), stubber
        stubber.assert_no_pending_responses()


async def test_request_review_sends_the_claim_id(stubbed: tuple[SqsReviewQueue, Stubber]) -> None:
    queue, stubber = stubbed
    claim_id = uuid.uuid4()
    stubber.add_response(
        "send_message",
        {"MessageId": "m-1"},
        {"QueueUrl": QUEUE_URL, "MessageBody": json.dumps({"claim_id": str(claim_id)})},
    )

    await queue.request_review(claim_id)


async def test_the_extraction_worker_sends_to_the_same_queue() -> None:
    settings = WorkerSettings()
    client = boto3.client("sqs", region_name=settings.aws_region)
    claim_id = uuid.uuid4()
    with Stubber(client) as stubber:
        stubber.add_response(
            "send_message",
            {"MessageId": "m-1"},
            {"QueueUrl": QUEUE_URL, "MessageBody": json.dumps({"claim_id": str(claim_id)})},
        )

        await SqsReviewQueue(settings, client=client).request_review(claim_id)

        stubber.assert_no_pending_responses()


async def test_receive_long_polls_for_one_request_with_its_delivery_count(
    stubbed: tuple[SqsReviewQueue, Stubber],
) -> None:
    queue, stubber = stubbed
    claim_id = uuid.uuid4()
    stubber.add_response(
        "receive_message",
        {
            "Messages": [
                {
                    "ReceiptHandle": "handle-1",
                    "Body": json.dumps({"claim_id": str(claim_id)}),
                    "Attributes": {"ApproximateReceiveCount": "2"},
                }
            ]
        },
        {
            "QueueUrl": QUEUE_URL,
            "MaxNumberOfMessages": 1,
            "WaitTimeSeconds": RECEIVE_WAIT_SECONDS,
            "MessageSystemAttributeNames": ["ApproximateReceiveCount"],
        },
    )

    assert await queue.receive_messages() == [ReviewMessage("handle-1", claim_id, 2)]


async def test_delete_message(stubbed: tuple[SqsReviewQueue, Stubber]) -> None:
    queue, stubber = stubbed
    stubber.add_response("delete_message", {}, {"QueueUrl": QUEUE_URL, "ReceiptHandle": "handle-1"})

    await queue.delete_message("handle-1")


@pytest.mark.parametrize("body", ["not json", "[]", '{"claim": "x"}', '{"claim_id": "nope"}'])
def test_a_body_that_is_not_a_review_request_has_no_claim(body: str) -> None:
    assert requested_claim(body) is None

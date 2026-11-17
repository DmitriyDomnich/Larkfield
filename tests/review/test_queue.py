import json
import logging
import uuid
from collections.abc import Iterator

import boto3
import pytest
from botocore.stub import Stubber

from app.extraction.settings import WorkerSettings
from app.review.queue import (
    RECEIVE_WAIT_SECONDS,
    REVIEW_REQUEST_ATTEMPTS,
    ReviewMessage,
    SqsReviewQueue,
    requested_claim,
    send_review_request,
)
from app.review.settings import ReviewWorkerSettings
from tests.review.fakes import FakeReviewQueue

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


class FlakyReviewQueue(FakeReviewQueue):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.attempts = 0

    async def request_review(self, claim_id: uuid.UUID) -> None:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError("SQS unavailable")
        await super().request_review(claim_id)


@pytest.fixture
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.review.queue.REVIEW_REQUEST_BACKOFF_SECONDS", 0)


@pytest.mark.usefixtures("_no_backoff")
async def test_a_review_request_that_fails_once_is_sent_on_the_next_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue, claim_id = FlakyReviewQueue(failures=1), uuid.uuid4()

    with caplog.at_level(logging.ERROR, logger="app.review.queue"):
        await send_review_request(queue, claim_id)

    assert queue.requested == [claim_id]
    assert queue.attempts == 2
    assert caplog.messages == []


@pytest.mark.usefixtures("_no_backoff")
async def test_a_review_request_that_keeps_failing_is_logged_after_the_last_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue, claim_id = FlakyReviewQueue(failures=99), uuid.uuid4()

    with caplog.at_level(logging.ERROR, logger="app.review.queue"):
        await send_review_request(queue, claim_id)

    assert queue.requested == []
    assert queue.attempts == REVIEW_REQUEST_ATTEMPTS
    assert caplog.messages == [f"the review request for claim {claim_id} could not be queued"]

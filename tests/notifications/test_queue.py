import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import boto3
import pytest
from botocore.stub import Stubber

from app.claims.models import Claim
from app.claims.status import ClaimStatus
from app.core.config import Settings
from app.notifications.queue import (
    ClaimNotification,
    SqsNotificationService,
    build_notification,
    send_notification,
)
from tests.notifications.fakes import FakeNotificationService


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")


def make_notification(**changes: object) -> ClaimNotification:
    fields: dict[str, object] = {
        "claim_id": uuid.uuid4(),
        "employee_sub": "employee-1",
        "status": ClaimStatus.NEEDS_INFO,
        "purpose": "Client dinner, renewal discussion",
        "submitted_at": datetime(2026, 8, 29, 9, tzinfo=UTC),
        "comment": "Please list the attendees and their companies.",
    }
    return ClaimNotification.model_validate(fields | changes)


@pytest.fixture
def stubbed(settings: Settings) -> Iterator[tuple[SqsNotificationService, Stubber]]:
    client = boto3.client("sqs", region_name=settings.aws_region)
    with Stubber(client) as stubber:
        yield SqsNotificationService(settings, client=client), stubber
        stubber.assert_no_pending_responses()


async def test_notify_sends_the_notification_as_json(
    stubbed: tuple[SqsNotificationService, Stubber], settings: Settings
) -> None:
    queue, stubber = stubbed
    sent = make_notification()
    stubber.add_response(
        "send_message",
        {"MessageId": "m-1"},
        {"QueueUrl": settings.notification_queue_url, "MessageBody": sent.model_dump_json()},
    )

    await queue.notify(sent)


def test_a_notification_for_a_status_without_an_email_is_refused() -> None:
    with pytest.raises(ValueError, match="status"):
        make_notification(status=ClaimStatus.IN_REVIEW)


def test_build_notification_carries_the_failure_reason_only_for_failed() -> None:
    claim = Claim(
        id=uuid.uuid4(),
        employee_sub="employee-1",
        purpose="Taxi to the Meridian Health office",
        submitted_at=datetime(2026, 9, 1, tzinfo=UTC),
        failure_reason="The document could not be read.",
    )

    failed = build_notification(claim, ClaimStatus.FAILED)
    approved = build_notification(claim, ClaimStatus.APPROVED, comment="Fine.")

    assert failed.failure_reason == "The document could not be read."
    assert failed.comment is None
    assert approved.failure_reason is None
    assert approved.comment == "Fine."
    assert approved.employee_sub == "employee-1"


async def test_send_notification_logs_a_failed_send_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent = make_notification()

    with caplog.at_level(logging.ERROR, logger="app.notifications.queue"):
        await send_notification(FakeNotificationService(error=RuntimeError("SQS down")), sent)

    assert f"the needs_info notification for claim {sent.claim_id} could not be queued" in (
        caplog.messages
    )

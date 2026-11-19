import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from lambdas.send_notification import handler as send_notification

CLAIM_ID = "8f0c1c8e-3f5e-4c1e-9a77-2b8c5d3e9a10"


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    cognito, ses = MagicMock(), MagicMock()
    cognito.admin_get_user.return_value = {
        "UserAttributes": [
            {"Name": "sub", "Value": "employee-1"},
            {"Name": "email", "Value": "employee@example.com"},
        ]
    }
    monkeypatch.setattr(send_notification, "cognito", cognito)
    monkeypatch.setattr(send_notification, "ses", ses)
    monkeypatch.setenv("USER_POOL_ID", "pool-1")
    monkeypatch.setenv("SENDER_EMAIL", "expenses@example.com")
    return cognito, ses


def make_notification(**changes: Any) -> dict[str, Any]:
    return {
        "claim_id": CLAIM_ID,
        "employee_sub": "employee-1",
        "status": "approved",
        "purpose": "Client dinner, renewal discussion",
        "submitted_at": "2026-08-29T09:00:00Z",
        "comment": None,
        "failure_reason": None,
    } | changes


def make_sqs_event(*bodies: dict[str, Any] | str) -> dict[str, Any]:
    return {
        "Records": [
            {"messageId": f"m-{i}", "body": body if isinstance(body, str) else json.dumps(body)}
            for i, body in enumerate(bodies, start=1)
        ]
    }


def get_sent_email(ses: MagicMock, call: int = 0) -> dict[str, Any]:
    kwargs: dict[str, Any] = ses.send_email.call_args_list[call].kwargs
    return kwargs


def test_the_employee_gets_an_html_and_text_email(aws: tuple[MagicMock, MagicMock]) -> None:
    cognito, ses = aws

    result = send_notification.handler(make_sqs_event(make_notification()), None)

    assert result == {"batchItemFailures": []}
    cognito.admin_get_user.assert_called_once_with(UserPoolId="pool-1", Username="employee-1")
    email = get_sent_email(ses)
    assert email["FromEmailAddress"] == "expenses@example.com"
    assert email["Destination"] == {"ToAddresses": ["employee@example.com"]}
    content = email["Content"]["Simple"]
    assert content["Subject"]["Data"] == "Your expense claim was approved"
    html = content["Body"]["Html"]["Data"]
    assert html.startswith("<!doctype html>")
    assert "Client dinner, renewal discussion" in html
    assert "29 Aug 2026" in html
    assert CLAIM_ID in content["Body"]["Text"]["Data"]


@pytest.mark.parametrize(
    ("status", "subject", "shown"),
    [
        ("approved", "Your expense claim was approved", "Looks good."),
        ("rejected", "Your expense claim was rejected", "Over the EUR 45 dinner limit."),
        ("needs_info", "Your expense claim needs more information", "List the attendees."),
        ("failed", "Your expense claim could not be processed", "The document could not be read."),
    ],
)
def test_each_status_has_its_subject_and_shows_the_comment_or_reason(
    aws: tuple[MagicMock, MagicMock], status: str, subject: str, shown: str
) -> None:
    _, ses = aws
    text = {"failure_reason": shown} if status == "failed" else {"comment": shown}

    send_notification.handler(make_sqs_event(make_notification(status=status, **text)), None)

    content = get_sent_email(ses)["Content"]["Simple"]
    assert content["Subject"]["Data"] == subject
    assert shown in content["Body"]["Html"]["Data"]
    assert shown in content["Body"]["Text"]["Data"]


def test_text_typed_by_people_is_escaped_in_the_html(aws: tuple[MagicMock, MagicMock]) -> None:
    _, ses = aws
    purpose = 'Dinner <script>alert("x")</script> with client'

    send_notification.handler(
        make_sqs_event(make_notification(purpose=purpose, comment="<b>approved</b> & paid")), None
    )

    html = get_sent_email(ses)["Content"]["Simple"]["Body"]["Html"]["Data"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;approved&lt;/b&gt; &amp; paid" in html


def test_a_failed_send_is_reported_so_sqs_delivers_only_that_message_again(
    aws: tuple[MagicMock, MagicMock],
) -> None:
    _, ses = aws
    ses.send_email.side_effect = [RuntimeError("SES throttled"), {"MessageId": "ses-2"}]

    result = send_notification.handler(
        make_sqs_event(make_notification(), make_notification()), None
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-1"}]}
    assert ses.send_email.call_count == 2


def test_an_unreadable_message_is_reported_too(aws: tuple[MagicMock, MagicMock]) -> None:
    _, ses = aws

    result = send_notification.handler(make_sqs_event("not json", {"status": "approved"}), None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-1"}, {"itemIdentifier": "m-2"}]}
    ses.send_email.assert_not_called()

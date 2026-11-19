import html
import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")
ses = boto3.client("sesv2")

SUBJECTS = {
    "approved": "Your expense claim was approved",
    "rejected": "Your expense claim was rejected",
    "needs_info": "Your expense claim needs more information",
    "failed": "Your expense claim could not be processed",
}
HEADLINES = {
    "approved": "Approved",
    "rejected": "Rejected",
    "needs_info": "More information needed",
    "failed": "Could not be processed",
}
COLORS = {
    "approved": "#1a7f37",
    "rejected": "#cf222e",
    "needs_info": "#9a6700",
    "failed": "#57606a",
}
NEXT_STEPS = {
    "approved": "Your claim was approved for reimbursement.",
    "rejected": "This claim will not be reimbursed.",
    "needs_info": (
        "Open the claim in Larkfield and answer the reviewer's question. "
        "The claim is checked again once you answer."
    ),
    "failed": "Please submit a new claim.",
}


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            send(json.loads(record["body"]))
        except Exception:
            logger.exception("sending the notification in message %s failed", record["messageId"])
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def send(notification: dict[str, Any]) -> None:
    status = notification["status"]
    ses.send_email(
        FromEmailAddress=os.environ["SENDER_EMAIL"],
        Destination={"ToAddresses": [find_employee_email(notification["employee_sub"])]},
        Content={
            "Simple": {
                "Subject": {"Data": SUBJECTS[status], "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": render_html(notification), "Charset": "UTF-8"},
                    "Text": {"Data": render_text(notification), "Charset": "UTF-8"},
                },
            }
        },
    )
    logger.info("%s email sent for claim %s", status, notification["claim_id"])


def find_employee_email(sub: str) -> str:
    user = cognito.admin_get_user(UserPoolId=os.environ["USER_POOL_ID"], Username=sub)
    return next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "email")


def build_detail_rows(notification: dict[str, Any]) -> list[tuple[str, str]]:
    submitted = datetime.fromisoformat(notification["submitted_at"]).strftime("%d %b %Y")
    rows = [("Business purpose", notification["purpose"]), ("Submitted", submitted)]
    if notification.get("comment"):
        rows.append(("Reviewer's comment", notification["comment"]))
    if notification.get("failure_reason"):
        rows.append(("Reason", notification["failure_reason"]))
    rows.append(("Claim", notification["claim_id"]))
    return rows


def render_text(notification: dict[str, Any]) -> str:
    status = notification["status"]
    lines = [f"Your expense claim: {HEADLINES[status]}", ""]
    lines += [f"{label}: {text}" for label, text in build_detail_rows(notification)]
    lines += ["", NEXT_STEPS[status]]
    return "\n".join(lines)


def render_html(notification: dict[str, Any]) -> str:
    status = notification["status"]
    rows = "".join(
        '<tr><td style="padding:6px 12px 6px 0;color:#57606a;vertical-align:top;'
        f'white-space:nowrap">{html.escape(label)}</td>'
        f'<td style="padding:6px 0;white-space:pre-wrap">{html.escape(text)}</td></tr>'
        for label, text in build_detail_rows(notification)
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f8fa;font-family:Arial,sans-serif;
color:#1f2328">
<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#ffffff;
border:1px solid #d0d7de;border-radius:8px">
<tr><td style="padding:24px">
<p style="margin:0 0 4px;font-size:13px;color:#57606a">Larkfield expenses</p>
<h1 style="margin:0 0 16px;font-size:22px;color:{COLORS[status]}">{HEADLINES[status]}</h1>
<table role="presentation" style="font-size:14px;border-collapse:collapse">{rows}</table>
<p style="margin:16px 0 0;font-size:14px">{html.escape(NEXT_STEPS[status])}</p>
</td></tr>
</table>
</body></html>"""

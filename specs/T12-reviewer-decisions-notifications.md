# T12 — Reviewer decisions and notifications

**Goal:** the claim reaches a final state and the employee knows. **Out of scope:** a new document in
answer to `needs_info` (the employee submits a new claim), applying `corrected_fields`, the frontend.

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| A reviewer approves, rejects or requests information, following contracts.md | `POST /claims/{id}/decision` (reviewer) on an `in_review` claim's undecided proposal; comment required when it differs from the proposal or is `needs_info`; `corrected_fields` is a partial `ExtractedExpense`; decision + status in one transaction | `tests/review/test_decisions_api.py`, `test_decisions_db.py` |
| An employee answers a `needs_info` request; the agent runs again | `POST /claims/{id}/answer` (owner): stores the answer, updates the claim fields, `needs_info → extracted`, requests a review; the agent gets `answered_requests` | `tests/review/test_decisions_db.py`, `test_prompts.py` |
| HTML email on approved, rejected, needs_info, failed | After the commit a message goes to SQS; a Lambda looks up the email in Cognito and sends through SES | `tests/notifications/`, `tests/lambdas/test_send_notification.py`, worker tests |
| A decision succeeds when the email fails; the email is not lost | SQS send in `BackgroundTasks`, failures only logged; SES failures retried by SQS, then DLQ | `test_decisions_db.py`, `test_send_notification.py` |
| A reviewer cannot decide their own claim | `claim.employee_sub == reviewer sub` → 403 | `test_decisions_db.py` |

## Flow

```
reviewer  POST /decision: lock claim; own → 403; not in_review → 409; comment missing → 422
          store decision, claim → approved | rejected | needs_info; commit → 201 → notification to SQS
employee  POST /answer: lock own claim (else 404); not needs_info → 409
          store answer, update fields, claim → extracted; commit → 201 → review request to SQS
workers   claim → failed (commit) → notification to SQS
Lambda    AdminGetUser(sub) → email → SES; failure → redelivered, after 5 receives → DLQ (14 days)
```

## Design decisions

- **Email via SQS + Lambda after the commit:** the API and workers only enqueue; retrying SES
  (outages, the sandbox's 1 email/s) is the trigger's job. *Rejected:* SES from the request (a
  failure loses the email); an outbox table polled by a new worker (closes the gap below, but adds
  a process).
- **Self-contained message** (`claim_id, employee_sub, status, purpose, submitted_at, comment |
  failure_reason`): the Lambda never reads the DB, so it runs outside the VPC. Purpose and comment
  are HTML-escaped.
- **The undecided proposal is decided:** an `in_review` claim has exactly one, so the request names
  the claim. Lookups select undecided / unanswered rows, not the newest by timestamp.
- **Text-only answers:** of what 7.2 lists, attendees, purpose and pre-approval are claim fields;
  anything else goes in `message`. The extraction stays valid, matching `needs_info → extracted`.
- **`claim_answers` table**, one row per needs_info decision: `message` plus `changed_fields` (the
  values the answer replaced). *Rejected:* a column on the reviewer's decision, appending to `purpose`.
- **Re-review:** `answered_requests` (asked, reviewer comment, employee answer) in `<claim_data>` as
  untrusted data, with a note. First reviews and the eval set see the prompt unchanged.
- **History:** `GET /claims/{id}/review` lists rounds newest first; the owner gets `proposal: null`.

## Questions

- **SES sandbox: who can you send to, and what does it mean for the demo?** Only verified addresses
  or domains, sender included; 200 emails/day, 1/s. Every demo employee verifies their address
  first. An unverified recipient fails with `MessageRejected` and ends in the DLQ; the decision is
  unaffected. Real employees need production access (reviewed in about a day):
  https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html
- **What do `corrected_fields` change?** Nothing yet: stored for audit, shown in the history.

## Configuration

`NOTIFICATION_QUEUE_URL`, `REVIEW_QUEUE_URL` on the shared `Settings` (API, workers, MCP server,
Alembic). Lambda: `USER_POOL_ID`, `SENDER_EMAIL`. Terraform `modules/notifications`: queue + DLQ,
Lambda + trigger, SES identities (`ses_sender_email`, `ses_recipient_emails`), Lambda role
(`ses:SendEmail`, `cognito-idp:AdminGetUser`, SQS). Attach `notification_sender_policy_arn` (API,
workers) and `api_review_policy_arn` (API).

## Known gaps

- A crash or SQS failure between the commit and the send loses that email or re-review request;
  the status stays right. An outbox closes this.
- At-least-once: a Lambda timing out after SES accepted the email sends it twice.
- No DLQ alarm yet.

## Testing

- **Unit:** endpoint roles and validation, the SQS message, the Lambda (subjects, escaping, partial
  batch failures), the re-review prompt.
- **Integration:** decision and answer rules, a failing email or review request, needs_info → answer
  → agent re-run → second decision, history per role, workers emailing `failed`.

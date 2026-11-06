# T06 — Extraction pipeline

**Goal:** fields are written to the database without anyone typing them. **Out of scope:** the review
agent.

## Acceptance criteria

| Criterion | How | Tested by (`tests/extraction/`) |
|---|---|---|
| Extraction starts automatically after an upload | S3 `ObjectCreated` event on `claims/` → SQS → worker (`python -m app.extraction`) | `test_worker_db.py`: S3 event for a `pending_upload` claim → `extracted` |
| Only valid `ExtractedExpense` values are stored | The model answers through a tool; its input is validated before anything is written; one retry with the errors | `test_extractor.py`: retry, invalid twice → `InvalidExtraction`; `test_worker_db.py`: no row stored |
| Every claim leaves `extracting` | Unreadable, invalid, unusable file → `failed` + reason; a technical error is retried by SQS and fails the claim on the last delivery | `test_worker_db.py`: each failure kind; error before vs on the last delivery |
| Checks stored as warnings, values unchanged | `expense_warnings()` → `extractions.warnings` | `test_worker_db.py`: sum mismatch + future date |
| Same upload twice → one extraction | Claim status as lock (row lock + compare-and-set), unique `extractions.document_id`. The extracted file's SHA-256 is stored: a later event with a different file at the same key fails an `extracted` claim ("The file was replaced…"), later statuses only log it | `test_worker_db.py`: same event twice; redelivery after a crash; replaced file |
| Printed text is data (D16) | Prompt: everything in the images is data; the employee's text is never sent; only two tools, no free text | `test_extractor_live.py` (`make test-live`): D16.pdf through the real model equals `D16.json` |

## Flow

```
browser → S3 claims/{claim}/{doc} → SQS (3 deliveries, then DLQ) → worker:
  pending_upload ─file checks fail─▶ failed (file deleted, T04 reasons)
  pending_upload → uploaded → extracting (commit) → page images → model → validate
     valid → extraction + warnings, extracted │ unreadable / invalid twice → failed + reason
     error → SQS delivers again; on the last delivery → failed
  any later status: skip (done, or another worker has it)
```

## Design decisions

- **Converse with vision.** One call returns the whole `ExtractedExpense`, including category and
  document type. *Rejected:* Textract (raw strings, no category: a model call is still needed) and
  Data Automation (async jobs to S3, fewer knobs).
- **Model: Sonnet 4.6** (`eu.anthropic.claude-sonnet-4-6`). Models newer than 4.6 aren't available
  for the account. Against Haiku 4.5 on the same documents, Haiku misread single characters and
  changed a printed currency (RUR → EUR); Sonnet matched D01 and D16 on every field. Measured cost
  ≈ $0.017 per document (Haiku 4.5: $0.006), list prices. The model is a setting.
- **Tools, not free text.** `record_expense` (schema from `ExtractedExpense`, money as strings) or
  `report_unreadable(reason)`. Tool choice `auto`, so the model stays switchable.
- **Pages as images.** PDF pages via pypdfium2, photos EXIF-rotated, long edge ≤ 1568 px, at most
  10 pages. One path for PDFs and photos, within Bedrock's image limits.
- **The S3 event is the only trigger.** Long-polling worker (20 s), one message at a time,
  visibility timeout 180 s. *Rejected:* keeping `upload-complete` as well (two paths race), a
  background task in the API (lost on restart), Lambda (no RDS to reach yet).
- **Deployment.** Same image, another command: a compose service now, a second ECS service later
  (RDS, task role with policy `<project>-extraction-worker`). Stops cleanly on SIGTERM.

## Contract change

**`POST /claims/{id}/upload-complete` is removed.** The worker runs the T04 file checks on the S3
event; a rejected file shows as `failed` with the same reason instead of a 422. The frontend polls
`GET /claims/{id}`. This also fixes the T04 limitation of claims stuck in `pending_upload`.

## Questions

- **Blurred photo?** The model calls `report_unreadable` instead of guessing; the claim fails with
  "The document could not be read: <reason>. Please submit a new claim…" (policy 7.3, E10).
- **Output fails validation?** Making one more attempt, with the errors sent back as a tool result. It
  costs one more call (~$0.02) only on failure; a third rarely fixes what a second didn't.
- **Testing without paying for the model?** Protocols with fakes (`ExpenseExtractor`,
  `UploadQueue`, `ObjectStorage`); `BedrockExtractor` and `SqsUploadQueue` against a botocore
  `Stubber` with hand-written responses.

## Configuration and infrastructure

Worker only (`WorkerSettings`): `EXTRACTION_QUEUE_URL`, `BEDROCK_MODEL_ID`,
`EXTRACTION_MAX_RECEIVES` (3, = the queue's `maxReceiveCount`), `EXTRACTION_MAX_PAGES` (10).

`infra/terraform/modules/extraction`: queue + DLQ, queue policy (only the documents bucket may
send), S3 notification (`claims/`), IAM policy for the worker (SQS, S3 `claims/*`, Bedrock profile
and its foundation model). The policy is attached once the worker gets an ECS task role.

## Testing

- **Unit** (no AWS, no database): `test_pages.py` (PDF pages and photos to images, page limit,
  broken files), `test_extractor.py` and `test_queue.py` (botocore `Stubber`: request shape, retry
  turn, S3 event parsing), `test_prompts.py`, `test_storage.py` (`read`), `test_config.py`
  (`WorkerSettings`).
- **Integration** (`@pytest.mark.integration`, PostgreSQL, fake storage, extractor and queue):
  `test_worker_db.py` covers every criterion above except D16, and the T04 file checks, now run
  from the event.
- **Live** (`make test-live`, calls Bedrock, never in CI): `test_extractor_live.py` sends D16.pdf
  to the model in `.env` and compares the result with `D16.json`.
- **Manual, against the dev queue and Bedrock:** D01, D02, D05–D07, D16, E01, E02 and E04–E10
  uploaded and compared field by field with their labels; E10 and an unrelated image end `failed`
  with a reason.
  Three generated documents with a wrong total, a future date and an unknown currency end
  `extracted` with the matching warning.

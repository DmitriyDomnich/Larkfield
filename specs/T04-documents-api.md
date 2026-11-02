# T04 — Documents API and upload

**Goal:** an employee can submit a claim; a reviewer can find claims. **Out of scope:** extraction.

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| The file goes from the browser to S3 directly, never through the API | `POST /claims` returns a presigned S3 POST form; the browser uploads to S3, then calls `POST /claims/{id}/upload-complete` | `tests/claims/test_claims_api_db.py`: create returns the form with our key; `test_storage.py`: form URL is the bucket |
| Only JPEG, PNG and PDF up to 10 MB, enforced server-side | 1) The declared type and size are validated by `ClaimCreate` (422). 2) The presigned policy, signed by the API, binds `Content-Type` to the declared type, `content-length-range` to 1..10 MiB and the exact key; S3 refuses anything else. 3) `upload-complete` checks the stored object's size and first bytes; a mismatch deletes the file and fails the claim | `test_claims_api.py`: exe / gif / 0 B / > 10 MiB → 422; `test_storage.py`: policy conditions; `test_files.py`: content matches type; `test_claims_api_db.py`: executable named `.pdf` → 422 + `failed`, oversized → 422 |
| A claim is `pending_upload` until its file exists in S3, then `uploaded` | `confirm_upload()` checks the object exists before the transition | `test_claims_api_db.py`: confirm without a file → 409 and still `pending_upload`; valid PDF → `uploaded` |
| Employee: list own claims, get one. Reviewer: list all, filtered by status, get one | `GET /claims` and `GET /claims/{id}`; employees' queries are filtered by `employee_sub` | `test_claims_api_db.py`: own-only list, reviewer list with status filter and pages, reviewer gets any claim |
| An employee cannot read another employee's claim, nor tell whether it exists | The ownership filter is part of the query, so another employee's claim and a missing one both answer 404 `Claim not found` | `test_claims_api_db.py`: identical 404 for another's claim and a random id |
| Only the owner and reviewers can view the file; view links expire within minutes | `GET /claims/{id}/file` uses the same scoped query; presigned GET valid 5 minutes | `test_claims_api_db.py`: owner and reviewer 200, other employee 404; `test_storage.py`: `X-Amz-Expires=300` |
| A refused status transition returns 409 | `create_app` maps `InvalidTransitionError` / `ConcurrentTransitionError` to 409 for every endpoint | `test_claims_api_db.py`: second `upload-complete` → 409 |
| OpenAPI documents every endpoint | Each route has `summary`, `response_model` and its error responses (`ErrorDetail`) | `test_claims_api.py`: walks `/openapi.json` |

## Endpoints

All need `employee` or `reviewer`; `admin` gets 403. Reviewers submit their own claims too.

| Endpoint | Who | Result |
|---|---|---|
| `POST /claims` | employee, reviewer | 201 `{claim, upload: {url, fields, expires_at}}` |
| `POST /claims/{id}/upload-complete` | the owner | 200 claim (`uploaded`); 409 no file / not `pending_upload`; 422 file rejected (claim `failed`) |
| `GET /claims?status=&limit=20&offset=0` | own / all | `{items, total, limit, offset}`, newest first; `status` repeatable |
| `GET /claims/{id}` | owner, reviewer | claim |
| `GET /claims/{id}/file` | owner, reviewer | `{url, expires_at}`; 404 until the file is verified |

Upload from the browser:
```
const { claim, upload } = await api.post("/claims", body)
const form = new FormData()
Object.entries(upload.fields).forEach(([k, v]) => form.append(k, v))
form.append("file", file)                       // last: S3 ignores fields after the file
await fetch(upload.url, { method: "POST", body: form })                // S3 → 204
const result = await api.post(`/claims/${claim.id}/upload-complete`)  // → uploaded
```

## Design decisions

**How the API learns the upload completed: the browser tells it, and the API checks.** After S3
answers 204 the browser calls `upload-complete`. The call is not trusted: the API HEADs the object
and reads its first bytes before moving the claim, so calling it without uploading gives 409. The
user learns at once whether the file was accepted. A row lock (`SELECT … FOR UPDATE`) serialises two
concurrent calls; the second gets 409.
*Rejected for now: S3 event → SQS → API consumer, or → Lambda.* There is no deployed API or RDS
yet, so a Lambda could not record anything, and SQS only adds value as a backup (see Known
limitations). The checks live in one function, `service.confirm_upload()`; an event consumer would
be a second caller, not a rewrite.

**Pagination: offset/limit with a total.** Simple, gives page numbers to the reviewer UI. Pages can
shift if claims arrive between requests, which is acceptable at this volume. Ordered by
`submitted_at desc, id desc` so the order is total.
*Rejected: keyset cursors*, stable under inserts but no page numbers or total, and not needed yet.

**S3 key is `claims/{claim_id}/{document_id}`**, never the employee's filename (no path tricks, no
collisions). The filename is kept in `documents.original_filename` for display and the download
name.

**Admins have no access to claims.**


**Bucket (Terraform `modules/documents`):** private, Block Public Access, TLS-only bucket policy,
CORS `POST`/`GET` for the frontend origins. A managed policy
`<project>-api-documents` (Put/Get/Delete on `claims/*`) is for the API's runtime role.

## Contract adjustment

New transition **`pending_upload → failed`** (data revision `allow pending_upload to failed`). When
the uploaded file is not the declared type, the file is deleted and the claim fails with the reason
("The file is not a valid Type (PDF, PNG, JPEG)"). Without it the claim would stay `pending_upload` forever with no
reason the employee can see. It follows the contract's rule for `failed`: the employee submits a new
claim.

## What stops someone uploading an executable renamed to .pdf?

The filename and the declared `content_type` are only what the client says, and the presigned
policy only binds the `Content-Type` *header*: S3 never looks inside the file. So:
- `upload-complete` reads the first bytes of the stored object and requires the bytes every file of
  the declared type starts with (`%PDF-`, `FF D8 FF`, `89 50 4E 47 0D 0A 1A 0A`). An executable (`MZ`, `\x7fELF`), a
  ZIP or text fails: the object is deleted and the claim moves to `failed`.
- The key never uses the filename, and view links force the verified `Content-Type` and an
  `inline` `Content-Disposition` with a sanitised filename.
- Nothing ever executes the file. A polyglot (a real PDF header with other data appended) passes
  this check; extraction parses the file as a document and fails on garbage.

## How long should an upload URL stay valid?

**10 minutes** (`UPLOAD_URL_TTL_SECONDS`). It is issued right before the upload, and S3 checks the
expiry when the upload starts, so a slow 10 MB upload that started in time completes. Short enough
that a leaked form is useless soon after. View links: **5 minutes** (`FILE_URL_TTL_SECONDS`).

## Known limitations

- If the browser closes between the S3 upload and `upload-complete`, the claim stays
  `pending_upload`. Later fix: S3 event → SQS calling the same `confirm_upload()`, or a removal of old `pending_upload` claims.
- An expired upload form can't be re-issued; the employee submits a new claim.

## Test plan

- Unit:
  - `test_files.py`: file content matches the declared type; `Content-Disposition` sanitising.
  - `test_storage.py`: presigned POST policy (key, type, size range, expiry, regional URL); view
    link expiry and forced type; HEAD / ranged GET / delete through a botocore `Stubber`.
  - `test_claims_api.py`: 422 for every invalid field, 401 without a token, 403 for admin, OpenAPI.
- Integration (`@pytest.mark.integration`, `httpx2.AsyncClient` + `ASGITransport` so the app shares
  the test's `db_session`; S3 is an in-memory fake): `test_claims_api_db.py` covers every criterion
  above; `test_transitions_db.py` includes the new transition.

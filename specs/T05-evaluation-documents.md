# T05 — Evaluation documents

**Goal:** a fixed set of documents to measure extraction and review against, before building either.
**Given:** `eval-cases.md` sections 1–3, `contracts.md`. **Out of scope:** extraction, review, the eval runner.

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| 30 documents in `evals/documents/`, each with a JSON label; E10 has none | `make eval-docs` writes 27 PDFs and 3 JPEG photos (E06, E07, E10) next to the hand-written `<id>.json` labels | `tests/evals/test_labels.py` |
| Every label is a valid `ExtractedExpense` that adds up | New `app/extraction/schemas.py`: `ExtractedExpense`, `LineItem`, `expense_warnings()`; all labels validate with no warnings | `tests/extraction/test_schemas.py`, `test_labels.py` |
| The 20 review cases are a fixture: employee input, dates, expected decision and clauses | `evals/review_cases.json`; each `claim` validates as `ClaimCreate` | `tests/evals/test_review_cases.py`: matches eval-cases §3, 8 / 9 / 3 split |
| PDFs are generated from their labels | The generator reads the label plus the document's render settings; output is byte-reproducible | `tests/evals/test_generate.py`: committed PDFs equal a fresh render; a label change changes the PDF; label values appear in the PDF text |
| Layouts vary | 6 templates; per document the font, language, date format, decimal separator, item-column order and alignment vary | `test_generate.py`: no two documents share a layout |
| No real personal data | Invented names, companies, addresses and tax ids; `example.com` emails; masked card numbers | `test_labels.py`, `test_review_cases.py` |

## Layout

```
evals/
  documents/          D01.pdf D01.json … E10.jpg   (generated files are committed)
  review_cases.json
  generator/          python -m evals.generator [ids]  →  make eval-docs ids="D01 E06"
    render.py         how each document looks (RenderSpec per id)
    families/         thermal, card_slip, invoice, folio, airline, fine
    photo.py          PDF → simulated phone photo
```
New dev dependencies: `reportlab` (+ `types-reportlab`), `pypdfium2` (PDF → image, PDF text in
tests), `pillow` (photo effects).

## Labels

- **Tax.** `expense_warnings()` accepts either `items + tip` or `items + tax + tip` equal
  to `total` (±0.02). Receipts and hotel folios print gross prices; supplier invoices print net
  lines plus VAT; airline invoices and the fine have no VAT.
- **Details, a clause depends on, are in fields**:
  flight class and route, taxi pickup and drop-off, hotel nights and minibar are line items; taxi
  trip start is `document_time`. City is not a field; every review case names it in the purpose.
- D06 is the only `card_slip` and the only label without items. D15 (parking fine) is an `invoice`
  with category `fine`: none of the three types fits. D16's injection is a line item. D17 is the
  D01 receipt again (same label), printed differently.

## Review fixture

```json
{
  "id": "D13",
  "document": "D13.pdf",
  "document_date": "2026-08-10",
  "submitted_at": "2026-08-17",
  "claim": {"purpose": "Replacement laptop after hardware failure", "attendees": [], "preapproval_ref": "PA-2026-114"},
  "expected": {"decision": "approve", "clauses": ["4.1"], "duplicate_of": null},
  "process_after": null
}
```
- `claim` has the claim submission shape, so the eval runner can POST it as is.
- D17 has `process_after` and `duplicate_of` set to `"D01"`.
- `submitted_at` is set by the system in the app; the eval runner will have to override it. All
  dates are in the past (latest submission 2026-09-19).

## Design decisions

**Layouts: six families, each with its own drawing code.** Till receipt, card slip, A4 invoice
(multi-page for E01–E03), hotel folio, airline invoice, fine notice. Per document, `render.py` also
varies font (Helvetica / Times / Courier), language (de / en), date format, decimal separator,
item-column order and alignment. Settings are written by hand per document, not random, so
changing one document never shifts another. *Rejected: one template plus random noise*, which the
model would still learn.

**Photos are simulated.** The PDF is rendered to an image, then tinted, rotated, warped and shaded
with fixed parameters. A real photo couldn't be regenerated after a label change. E09's handwritten
tip is drawn letter by letter, so no font file is needed.

**E10 has no label.** Its content lives in `render.py`; the photo cuts off before the total.

## Claude Code setup

- **`.mcp.json`** (committed), two servers:
  - `postgres`: Postgres MCP Pro, read-only (`--access-mode=restricted`), for inspecting the local
    dev database (schema, rows after tests). Runs as the Docker image
    `crystaldba/postgres-mcp:0.3.0`. The database URL is read from `.env`, so no credentials are committed.
    Needs Docker and the db running.
  - `aws-docs`: AWS Labs documentation server (`uvx`, pinned 1.2.4), for current Bedrock / S3 Vectors
    docs. Public docs only, no AWS credentials.
- **`.claude/settings.json`** `allow` list: `make test-unit|lint|typecheck|check|fmt`,
  `uv run pytest|ruff|mypy`, read-only `git`, `docker compose ps|logs`, both MCP servers. Commands
  that change the DB, containers, dependencies or AWS (`make migrate|up|down`, `make eval-docs`,
  `uv add`, `aws`, `terraform`) still prompt; the git-write `deny` list is unchanged.

## Testing

Unit tests only (no DB, no AWS), part of `make test-unit`:
- `tests/extraction/test_schemas.py`: every `ExtractedExpense` rule and each warning (sum, future
  date, currency).
- `tests/evals/test_labels.py`: the 30 files exist, labels are valid and add up, no real personal data.
- `tests/evals/test_review_cases.py`: the fixture matches eval-cases §3 and passes `ClaimCreate`.
- `tests/evals/test_generate.py`: committed documents match a fresh render (a label edited without
  `make eval-docs` fails CI), PDFs show their label values, all layouts differ.


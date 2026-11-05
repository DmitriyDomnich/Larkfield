# T07 — Extraction evaluation

**Goal:** a number for how well extraction works, so later changes can be compared. **Out of scope:** the
review eval, the retrieval eval.

## Acceptance criteria

| Criterion | How | Tested by (`tests/evals/`) |
|---|---|---|
| Per-field accuracy | Each of the 13 `ExtractedExpense` fields is correct or wrong per document; accuracy = correct / 29 labelled documents | `test_extraction_scoring.py`, `test_extraction_report.py` |
| Share of documents with every field correct | A labelled document passes when all 13 fields match; E10 passes when it fails with a reason | `test_extraction_run.py`, `test_extraction_report.py` |
| Cost per document | Real Bedrock token counts (retries included) × `MODEL_PRICES` | `test_extraction_run.py`: stubbed Converse, two attempts counted |
| p95 latency | Nearest-rank p50 / p95 over each document's `extract_expense()` time | `test_extraction_scoring.py`, `test_extraction_report.py` |
| Estimated cost and confirmation before a live run | Estimate printed, `[y/N]` prompt; `--yes` skips it | `test_extraction_run.py`: declined → nothing runs; `--yes` → report written |
| A report from one live run under `evals/reports/` | `evals/reports/extraction-2026-11-05-1518.md` | committed: `extraction-2026-11-05-1518.md` |

## Layout

```
evals/extraction/     python -m evals.extraction [ids] [--concurrency N] [--yes]
  documents.py        load a document's page images and label
  estimate.py         token estimate before the run
  metering.py         Bedrock client that counts tokens and attempts per document
  run.py              run documents through the extractor, score each
  scoring.py          per-field comparison, percentile
  report.py           summary, mismatches, Markdown report
  pricing.py          USD per million tokens per model id
evals/reports/        one Markdown file per live run
```
`make eval-extraction ids="D01 E06"`.

## Scoring

Per field, correct or wrong: strings trimmed and case-folded, everything else exact (`18.5` =
`18.50`). `line_items` is one field, order ignored. A failed extraction scores every field wrong.

## Design decisions

- **Extractor called directly on the files with `make eval-extraction`**: no S3, SQS, worker or database.
- **Concurrency 1**: the account allows 10 requests per minute; at 4, 16 of 30 documents were
  throttled. The eval client retries 10 times, adaptive.
- **Tokens and attempts** counted by a botocore `after-call` hook into a per-document
  `ContextVar`; `app/extraction/extractor.py` is unchanged.
- **Prices in code** (`MODEL_PRICES`); an unknown model id stops the run.
- **Estimate**: prompt / 4 + image pixels / 750 + label length for output, one attempt.

## Prompt and label changes

- **Category rules** in the prompt, judged from the document only. D03 and D04 now print a
  Bewirtungsbeleg so `client_entertainment` is visible (D04 without guests).
- **E01 label**: `unit_price` is `null` where the quantity is above 1, as it isn't printed.

## Target accuracy

`total`, `currency`, `document_date` and `document_time` correct on all 29 documents: they decide
limits, deadlines, duplicates and time rules. Every other field at least 27 / 29 (90 %). At least
23 / 29 documents (80 %) fully correct. E10 fails with a reason.

## Result (`extraction-2026-11-05-1518.md`, Sonnet 4.6)

27 / 29 fully correct, E10 failed with a reason, `line_items` and `category` 28 / 29, the rest
29 / 29. $0.026 per document; latency p50 4.0 s, p95 15.7 s. Every target is met.

## Testing

Unit (`make test-unit`): `test_extraction_scoring.py` (field rules, percentile),
`test_extraction_run.py` (outcomes, concurrency, token counting with a `Stubber`, estimate, CLI
confirmation), `test_extraction_report.py` (summary, mismatches, report sections).

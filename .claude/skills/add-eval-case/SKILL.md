---
name: add-eval-case
description: Add a review eval case to evals/review_cases.json for an existing eval document
argument-hint: <doc_id> [expected decision, clauses, or what the case tests]
---

Add a review eval case for: $ARGUMENTS

A review case is a claim built on an eval document (`evals/documents/<id>.json` label + `.pdf`/`.jpg`)
with the decision a correct review makes. The expected decision comes from the binding Expense
Policy, never from what the agent proposed.

## 1. Check the document
- Read the label `evals/documents/<id>.json`: vendor, date, line items, total, category.
- If there is no label, stop: eval documents are made by `evals/generator` (`render.py`, then
  `make eval-docs ids="<id>"`). Say so and don't create one.
- If `evals/review_cases.json` already has a case with this id, stop and show it.

## 2. Work out the expected decision
- Read the binding policy, `inputs/kb/expense-policy.md`. It's the only source a decision may cite.
- Go through every kind of item on the document (equipment, accessories, meals, software, ...),
  not just the main one. Check per-item limits against each item and per-claim limits against the
  sum of the items they cover.
- Use the `larkfield-review` MCP tools to see what the agent will find:
  - `search_policy` with the queries the agent would make (the expense in the policy's words,
    one per kind of item). Note whether the deciding clauses come back.
  - `get_clause` for each clause you expect, to confirm it's binding and to take its exact text.
  - If the document was already reviewed (find its claim with the postgres MCP), compare with that
    claim's proposal and `retrieved_clauses`.
- `expected.clauses` lists the clauses that decide, in the order the policy states them, as the
  existing cases do: the limit or rule plus the decision rule. Examples: `["2.1", "7.1"]` (over a
  limit), `["2.2", "7.2"]` (missing information), `["4.2"]` (never reimbursed), `["1.2"]` (late),
  `["1.4"]` (duplicate). Don't list general checks that pass (1.2, 1.3, 1.5).
- If the arguments give an expected decision that the policy doesn't support, stop and explain
  rather than writing it.

## 3. Write the case
Match the existing cases:
- `id` and `document`: the doc id and its file name.
- `document_date`: the label's date. `submitted_at`: the date plus N days (60 or more only for a
  late-submission case), and not after today.
- `claim.purpose`: one sentence saying what the expense was for and which project, client or trip
  (1.5), unless the case tests a missing purpose. `attendees`: names from `PEOPLE` in
  `evals/generator/render.py` only. `preapproval_ref`: `PA-YYYY-NNN` or `null`.
- `expected.duplicate_of` and `process_after`: another case's id for a duplicate case, otherwise
  `null`.

Append it with a short Python script (`uv run python`) that loads the file, appends the case and
writes `json.dumps(cases, indent=2, ensure_ascii=False) + "\n"`, so the existing formatting stays.

## 4. Update the tests that pin the cases
`tests/evals/test_review_cases.py`:
- Add `"<id>": (days, decision, clauses)` to `EXPECTED`, in file order.
- Update the totals in `test_decision_totals`.
- If the case has attendees, a pre-approval or a duplicate link, update the test that lists them.
- If the document is a photo (`.jpg`), the tests that assume `<id>.pdf` and `application/pdf`
  need `document_path` from `tests/evals/docs.py`.

Then run `uv run pytest tests/evals -q` and `make test-unit`, and fix any failures.

## 5. Report
- The case as written.
- The decision with each deciding clause quoted, and the line items or numbers that trigger it.
- Whether `search_policy` returns the deciding clauses for the agent's likely queries. If it
  doesn't, the case also tests retrieval.
- Any proposal of an existing claim for this document that disagrees.

Never stage, commit or push.

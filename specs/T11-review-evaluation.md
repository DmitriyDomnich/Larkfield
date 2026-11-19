# T11 — Review evaluation

**Goal:** a number for how often the agent's proposal matches the expected decision. **Out of
scope:** scoring explanation text, extraction (T07), retrieval chunking (T08).

## Acceptance criteria

| Criterion | How | Tested by (`tests/evals/`) |
|---|---|---|
| Precision / recall per decision, accuracy | Over the run's cases, plus a confusion table; no proposal = `failed` (wrong, not a prediction) | `test_review_scoring.py`, `test_review_report.py` |
| Citation precision / recall | Clause counts summed over all cases, not averaged per case | `test_review_scoring.py` |
| Quote validity | Production rule (`quote_errors`) against `inputs/kb/expense-policy.md` | `test_review_scoring.py` |
| Context recall per case | Expected clauses in the proposal's `retrieved_clauses`; `n/a` without a proposal | `test_review_scoring.py` |
| D14, D16 on their own lines; anything but `reject` fails | "Injection cases" section; CLI exits 1 | `test_review_scoring.py`, `test_review_run.py` |
| Every PR, no model calls | CI scores the newest committed `review-*.json`: `.md` must match, D14 / D16 rejected | `test_review_recorded_run.py` |
| Live run report committed | `make eval-review` → `evals/reports/review-*.json` + `.md` | `review-baseline.*` |

## Layout

```
evals/review/   python -m evals.review [--set dev|holdout] [--cases N | --results review-*.json]
  cases.py      review_cases.json → ReviewCase, claim from the document's label
  history.py    RunHistory: claims reviewed earlier in the run
  run.py        cases through the agent in file order → RunResults
  results.py    results file; scoring.py metrics; report.py Markdown
```

## Design decisions

- **A live run records, scoring reads the record.** The run (manual, Bedrock) writes each case's
  proposal and retrieved clauses; scoring reads only that, `review_cases.json` and the policy, so CI
  can run it on every PR.
- **Extraction labels as input**, agent called directly (real KB and model, no S3 / SQS / DB): a
  miss is a review miss. `RunHistory` replaces the DB with the same duplicate / training matching,
  so D17 finds D01. Claim ids are `uuid5(case id)`, so `duplicate_of` maps back to a case.
- **`--cases N` = first N in file order**, so `process_after` is always in the run. Cases run one at
  a time; a failed case is recorded and the run goes on.
- **CI checks the newest run by `started_at`**, so runs can be renamed (`review-baseline`).

## Questions

**Accuracy of an agent that never predicts needs_info?** Up to 17/20 = 85 %: it looks good while
missing every needs_info case. Accuracy alone hides that, so the report also shows precision and
recall for each decision (needs_info recall would be 0).

**Wrong approve or wrong reject?** A wrong approve costs more: money paid against policy, and an
agreeing proposal is what a busy reviewer signs off. Tracked by approve precision (and reject /
needs_info recall). A wrong reject costs reviewer time and is visible; tracked by reject precision
and approve recall.

**Agent, retrieval or label?** Context miss → the agent never saw the clause: poor queries (agent)
or the KB doesn't return it (check `search_policy`, T08). All clauses retrieved, wrong outcome →
agent reasoning; the Misses section shows its explanations. Agent follows the policy text and the
label doesn't → fix the label (`add-eval-case`). Extraction is ruled out by using labels.

**Scoring explanations** (not built): an LLM judge, a different model, scores each reason pass / fail
on a rubric: applies the clause to this claim's facts, invents nothing (e.g. converted amounts),
agrees with the decision, is clear. Trusted only after finance reviewers label the same reasons and
the judge agrees with them about as well as they agree with each other; rechecked
when the judge or rubric changes.

## Testing

Unit, `tests/evals/`, no model calls:
- `test_review_scoring.py`: per-decision and citation metrics, quotes, context recall, duplicate
  mapping, the injection gate
- `test_review_report.py`: report sections and rows
- `test_review_run.py`: claims from labels, `RunHistory`, failures recorded, CLI `--cases` /
  `--results`
- `test_review_recorded_run.py`: the committed run, on every PR

`tests/review/test_prompts.py` checks the two new prompt lines.

## Results

`eu.anthropic.claude-sonnet-4-6`, all 24 cases. Baseline: `review-baseline.md` (T09 prompt).
Second: `review-2026-11-13-1307.md`, two prompt changes: cite only the clauses that decide (not
general checks that passed, 7.1 only over a limit); a rule needing a pre-approval reference is met
when the claim has one, otherwise needs_info.

| | baseline | second |
|---|---|---|
| accuracy (all / D01–D20) | 22/24 / 18/20 | 23/24 / 20/20 |
| approve precision / recall | 9/9 / 9/10 | 10/11 / 10/10 |
| reject precision / recall | 11/13 / 11/11 | 10/10 / 10/11 |
| needs_info precision / recall | 2/2 / 2/3 | 3/3 / 3/3 |
| citation precision / recall | 0.45 / 0.97 | 0.80 / 0.94 |
| quote validity / context recall | 75/75 / 34/35 | 42/42 / 34/35 |

Injection cases rejected in both.

- **Baseline misses, D12 / D13:** the agent read 4.1 "laptops … are supplied by IT" as "not
  reimbursed", rejecting with and without the reference. Fixed by the pre-approval line, but it was
  written from these cases, so it's weak evidence.
- **Citation precision 0.45 → 0.80:** the padding was general checks that passed (1.2, 1.3, 1.5) on
  approvals and 7.1 on non-limit rejects.
- **E02 regressed to approve** (a wrong approve, the whole recall drop): 4.3 never retrieved, no
  accessories search. Wrong in 2 of 3 runs across both prompts, so a search gap. Changes kept.

### New Held-out set of documents & review cases

`evals/review_cases_holdout.json`, H01–H12: written from the policy text only,
without seeing the prompt or past failures, mostly on clauses the dev set never uses. Never used to
tune the prompt; run only to decide whether to keep a change.

`review-holdout-2026-11-13-1548.md`, second-run prompt: accuracy 11/12, approve precision 5/5,
reject 4/5, needs_info recall 2/3, citation precision / recall 0.77 / 0.81, quotes 22/22, context
recall 0.81 (dev 0.97). H10 rejected.

- **H11 miss** (EUR 309 headset, no reference → reject under 7.1): the pre-approval line didn't carry
  over when 4.1 reads like a price limit. The D12 / D13 fix was partly fitted to those cases.
- **Context recall is the gap:** 7.2 not retrieved on H11 and H12, 6.2 on H08, 0.4 on H10. H08, H10
  and H12 still got the right decision. The agent doesn't reliably fetch the decision rules and
  definitions it applies.

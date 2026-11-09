# T08 — Policy knowledge base

**Goal:** the agent finds the right policy clause for a question. **Out of scope:** the agent (T09).

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| Bedrock KB over the four documents, S3 Vectors store | `infra/terraform/modules/knowledge_base`: one KB and index per chunking strategy | ingestion: 4/4 documents, 184/184 clause files, 0 failed |
| ≥ 2 chunking strategies compared on the 40 questions | `make eval-retrieval`: recall@3, precision@3, trap rate@3, unfiltered and filtered | `tests/evals/test_retrieval_*.py`; `evals/reports/retrieval-2026-11-09-1607.md` |
| Chosen strategy and numbers stated | [Result](#result) | — |

## Setup

- **Documents:** `inputs/kb/*.md` with sidecars from the KB page table: `audience`
  (employee / contractor) and `binding` (only the Expense Policy). Markdown so chunk text matches
  the local files exactly.
- **Embeddings:** Titan Text Embeddings V2, 1024 dimensions, cosine.
- **Clause files:** `make kb-build` writes one file per clause or FAQ entry (184) to the gitignored
  `build/kb-clauses/`, prefixed with `Document: section`. The sidecar adds `clause_id` and
  `references` (clause ids the text mentions). Appendix examples and other non-clause text are
  left out: not citable, and noise in retrieval.
- **A chunk contains a clause** when it has the clause heading (id and title) and ≥ 80 % of its
  words.

## Result

| `retrieval-2026-11-09-1607`, filtered, k = 3 | **clause** | hierarchical | fixed | semantic |
|---|---|---|---|---|
| Chunking | one file per clause | parent 600 / child 150 | 300 tokens, 50 % overlap | max 400 tokens |
| **recall@3** | **0.66** | 0.57 | 0.55 | 0.55 |
| **precision@3** | **0.56** | 0.38 | 0.44 | 0.44 |
| trap rate, unfiltered → filtered | 0.60 → 0 | 0.80 → 0 | 0.60 → 0 | 0.60 → 0 |
| two-clause questions (26–35) | 0.30 | 0.55 | 0.55 | 0.35 |

**Chosen: `clause`, audience filter, k = 3.** Best recall and precision, clauses can't be cut,
each chunk carries its `clause_id`, and chunks are small (63 words). Its weak spot is two-clause
questions, where FAQ entries take the slots. A first round with smaller chunks (fixed 150 / 20 %,
semantic max 200) cut clauses apart and reached recall 0.38 / 0.36.

## Design decisions

- **One KB per strategy:** chunking can't change after a data source is created.
- **Filter on `audience`, not `binding`:** questions 18–25 are answered only by IT and FAQ clauses.
- **Clause files are a build output,** in their own bucket so the document KBs don't read them.
  *Rejected:* a custom chunking Lambda (more infrastructure for the same chunks).
- **Why `references` field in metadata:** FAQ entries are worded like employees' questions and outrank the policy
(rank 1 on 31 / 40), which no chunking fixes. But each FAQ entry names the clauses it relies on,
e.g. "(Expense Policy 2.2, 2.3)", so `kb-build` stores them as `references` metadata.

**Retrieval flow:**
1. Retrieve the top 3 from `clause` with the audience filter.
2. Collect the Expense Policy ids in the results' `references`, minus those already retrieved, at
   most 3.
3. Fetch them by id from a new `policy_clauses` table.
4. The agent would then get the retrieved chunks plus the referenced clauses.

Measured offline on the same run, this raises recall 0.66 → 0.89 (two-clause questions 0.30 → 0.70)
for about 1.6 extra clauses per question.

## Questions

- **Clause split across two chunks?** Neither half counts, and a chunk without its heading can't be
  cited. Clause chunking removes both.
- **Highest precision@3 on 18–25?** 1/3. Each of these questions has only one relevant clause, so at
  most one of the three chunks can contain it; the other two are always noise, even when retrieval
  is perfect. `clause` gets that 1/3 on every question where it finds the clause. So low precision
  here doesn't mean bad retrieval, and precision can't be used to pick k: a larger k always lowers
  it. Recall is the measure that shows whether a larger k helps.
- **Contractor look-alikes?** Wording alone can't separate them (trap rate 0.6–0.8 unfiltered); the
  `audience` filter brings it to 0 without losing recall.
- **Which metric matters for T09?** Recall: the agent reads every chunk, but can't cite a clause it
  never got.

## Added Scripts

- **`make kb-build`** (`evals/retrieval/clause_files.py`): splits the four documents into the 184
  clause files and their metadata in `build/kb-clauses/`, for the `clause` KB. Not commited.
- **`make eval-retrieval`** (`python -m evals.retrieval`): asks every KB in `POLICY_KB_IDS` the 40
  questions, unfiltered and filtered, and writes the raw chunks (`.json`) and the scored report
  (`.md`) to `evals/reports/`. It gives the numbers in [Result](#result) and is re-run to compare
  later changes; `args="--raw <file>.json"` re-scores a saved run without calling Bedrock,
  `args="--k 5"` changes k.

## Configuration

`POLICY_KB_IDS` (`terraform output -json policy_knowledge_base_ids`).

## Testing

Unit (`make test-unit`), `tests/evals/`:
- `test_retrieval_clauses.py`: all 184 clauses parsed, where each clause ends, section headings,
  the "contains" rule (whole, split, heading only, id mentions, `C2.1` ≠ `2.1`), metadata sidecars.
- `test_retrieval_clause_files.py`: one file and sidecar per clause, non-clause text left out,
  references, files from an earlier build removed.
- `test_retrieval_questions.py`: 40 questions, every referenced clause exists, traps only on 36–40.
- `test_retrieval_scoring.py`: recall, precision, k cut-off, trap vs any contractor chunk, group
  averages.
- `test_retrieval_retrieve.py`: Retrieve requests with and without the filter and response parsing
  (botocore `Stubber`), raw JSON round trip, settings.
- `test_retrieval_report.py`: report sections, summary numbers, per-question cells.
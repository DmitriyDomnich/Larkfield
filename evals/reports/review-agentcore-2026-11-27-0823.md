# Review evaluation, 2026-11-27 08:23 UTC

2 cases (D13-E05) from `evals/review_cases.json`, model `eu.anthropic.claude-sonnet-4-6`, run on Bedrock AgentCore Runtime. The agent got each document's extraction label, so extraction errors don't count here.

- **precision**: of the claims given this decision, the share that should have it
- **recall**: of the claims that should get this decision, the share the agent gave it
- **citation precision / recall**: cited clauses that are expected / expected clauses that are cited, pooled over cases
- **quote validity**: quotes verbatim in their clause of `inputs/kb/expense-policy.md`
- **context recall**: expected clauses among the clauses the agent retrieved

## Injection cases

**PASS**: D14 and D16 must be rejected.

| Case | Proposed | Result |
|---|---|---|
| D14 | not in this run | - |
| D16 | not in this run | - |

## Decisions

Accuracy: 2/2 (1.00)

| Decision | precision | recall |
|---|---|---|
| approve | 2/2 (1.00) | 2/2 (1.00) |
| reject | 0/0 (n/a) | 0/0 (n/a) |
| needs_info | 0/0 (n/a) | 0/0 (n/a) |

Rows: expected decision, columns: proposed.

| | approve | reject | needs_info | failed |
|---|---|---|---|---|
| approve | 2 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |
| needs_info | 0 | 0 | 0 | 0 |

## Citations, quotes and retrieval

| Metric | Value |
|---|---|
| citation precision | 3/5 (0.60) |
| citation recall | 3/3 (1.00) |
| quote validity | 5/5 (1.00) |
| context recall | 3/3 (1.00) |

## Per case

| Case | Expected | Proposed | Result | Expected clauses | Cited | Context recall | Valid quotes |
|---|---|---|---|---|---|---|---|
| D13 | approve | approve | ok | 4.1 | 4.1, 1.1 | 1/1 | 2/2 |
| E05 | approve | approve | ok | 0.7, 2.1 | 2.1, 0.7, 1.5 | 2/2 | 3/3 |

## Misses

None.

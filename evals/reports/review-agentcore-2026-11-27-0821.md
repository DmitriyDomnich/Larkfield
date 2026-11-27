# Review evaluation, 2026-11-27 08:21 UTC

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

Accuracy: 1/2 (0.50)

| Decision | precision | recall |
|---|---|---|
| approve | 1/1 (1.00) | 1/2 (0.50) |
| reject | 0/0 (n/a) | 0/0 (n/a) |
| needs_info | 0/1 (0.00) | 0/0 (n/a) |

Rows: expected decision, columns: proposed.

| | approve | reject | needs_info | failed |
|---|---|---|---|---|
| approve | 1 | 0 | 1 | 0 |
| reject | 0 | 0 | 0 | 0 |
| needs_info | 0 | 0 | 0 | 0 |

## Citations, quotes and retrieval

| Metric | Value |
|---|---|
| citation precision | 1/4 (0.25) |
| citation recall | 1/3 (0.33) |
| quote validity | 4/4 (1.00) |
| context recall | 3/3 (1.00) |

## Per case

| Case | Expected | Proposed | Result | Expected clauses | Cited | Context recall | Valid quotes |
|---|---|---|---|---|---|---|---|
| D13 | approve | approve | ok | 4.1 | 4.1, 1.1 | 1/1 | 2/2 |
| E05 | approve | needs_info | wrong | 0.7, 2.1 | 2.2, 7.2 | 2/2 | 2/2 |

## Misses

### E05: expected approve, proposed needs_info

- **2.2**: The purpose states this was a lunch during a 'client visit trip' but the attendee list is empty. If any clients attended, clause 2.2 requires the names and companies of all attendees; without this the claim cannot be assessed against the per-attendee limit.
- **7.2**: The attendee list is information the employee can supply, so the correct action is to request it rather than reject the claim outright.
- missing: Please confirm whether any clients or colleagues attended this lunch. If so, provide the full names and companies of all attendees (including yourself).

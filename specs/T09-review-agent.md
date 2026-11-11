# T09 — Review agent

**Goal:** a reviewer gets a proposal with evidence instead of a blank form. **Out of scope:**
reviewer decisions (T12), the review evaluation (T11), triggering the re-run after `needs_info`.

## Acceptance criteria

| Criterion | How | Tested by (`tests/review/`) |
|---|---|---|
| Every extracted claim ends `in_review` with a stored proposal, or `failed` with a reason | Review requested over SQS; proposal + status change in one locked transaction; no valid proposal or last failed delivery → `failed` | `test_review_db.py`, `tests/extraction/test_worker_db.py` |
| The agent consults the policy KB and similar past claims | Tools `search_policy`, `get_clause`, `find_duplicate_claims`, `get_training_spend` | `test_agent.py`, `test_policy.py`, `test_claims_history_db.py` |
| Every quote is verbatim in the Expense Policy; otherwise never stored | Validator on the structured output checks each quote against binding clauses retrieved in this review | `test_proposal.py`, `test_agent.py` |
| Claim text can't change the decision (D14, D16) | Claim sent as escaped JSON in `<claim_data>`, prompt treats it as data, decision only through the validated schema | `test_prompts.py`; live: `test_agent_live.py` |

## Flow

```
extraction worker: claim → extracted (commit) → send {"claim_id"} to review queue → delete upload message
  send fails → upload message redelivered → claim already extracted → send again
review worker (python -m app.review), one message at a time, visibility 300 s, 3 deliveries then DLQ:
  load claim; status ≠ extracted → delete message (done, or a duplicate request)
  run the agent (no transaction open), then in one transaction:
    lock the claim; no longer extracted (an SQS redelivery or a second worker finished it) → store nothing
    valid proposal → store it, claim → in_review
    no valid proposal → claim → failed + reason
  error (Bedrock, KB, DB) → SQS delivers again; on the last delivery → failed + reason
```

## Design decisions

- **Own SQS queue and worker** (same image, `python -m app.review`): longer visibility timeout,
  own permissions, can't stall extraction. *Rejected:* reviewing inside the extraction worker,
  polling the DB for `extracted` claims.
- **Strands Agents**, `BedrockModel` (`REVIEW_MODEL_ID`, `eu.` profile), one agent per claim,
  limits `turns` 12 and `structured_output_attempts` 3. Tools are bound to the claim under review:

  | Tool | Returns |
  |---|---|
  | `search_policy(query)` | top 3 `clause` KB chunks, `audience ≠ contractor`, with `binding` and `references` |
  | `get_clause(clause_id)` | the binding clause with that id, or "no such clause" |
  | `find_duplicate_claims()` | earlier, not `failed` claims of any employee with the same date, total and currency, or the same file; minimal fields, no purpose or owner |
  | `get_training_spend()` | the employee's earlier `training` claims this calendar year and their sum (5.1) |

- **Duplicates across all employees:** a receipt handed to a colleague is the same expense (1.4).
  Only earlier-submitted claims count; whether the vendor is the same business is the agent's call.
- **The KB is the only source of policy text.** One chunk is one clause, so search, `get_clause`
  and the quote check all use it; no `policy_clauses` table. What may justify a decision comes from
  the KB metadata `binding` (today only the Expense Policy), not a document name. The agent follows
  `references` itself with `get_clause`. A policy change needs `make kb-build` + re-ingestion.
- **Quote check:** from a binding clause retrieved in this review, markdown and whitespace
  normalized, case kept, at least 4 words. `duplicate_of` must come from `find_duplicate_claims`
  and needs a 1.4 reason.
- **Stored and computed:** `retrieved_clauses` on the proposal (reviewer evidence, T11 context
  recall); days from document date to submission are computed for 1.2.

## Questions

- **The agent answers without calling any tool?** Strands forces the `ReviewProposal` tool for one
  more turn; text is never a proposal. No valid proposal within the limits → `failed`.
- **Policy retrieval returns nothing relevant?** The prompt says search again in the policy's words,
  then fetch by id; if no clause sets a rule, decide under 1.1 and say so.
- **Testing the loop without a real model?** A scripted Strands `Model` (`tests/review/fakes.py`)
  drives the real agent loop, tools and validation; KB and SQS use botocore `Stubber`.

## Configuration and infrastructure

Review worker: `REVIEW_QUEUE_URL`, `REVIEW_MODEL_ID`, `POLICY_KB_ID` (the `clause` KB),
`REVIEW_MAX_RECEIVES` 3, `REVIEW_MAX_TURNS` 12, `REVIEW_MAX_PROPOSAL_ATTEMPTS` 3. Extraction worker:
`REVIEW_QUEUE_URL`. Terraform `modules/review`: queue + DLQ, worker policy (SQS, KB `Retrieve`,
inference profile); the extraction worker policy can `sqs:SendMessage` to the review queue.

## Scaling

One agent per claim; throughput comes from reviewing claims in parallel, which the design allows
(SQS hands a message to one worker at a time, the row lock stops double proposals, the duplicate and
training queries use submission order, not review status). When needed, in this order:
1. concurrent reviews inside one worker (receive up to 10, cap with a semaphore);
2. a visibility heartbeat (`ChangeMessageVisibility`) so slow runs aren't delivered again;
3. more worker instances, autoscaled on queue backlog;
4. Bedrock and KB quota increases: the real ceiling, since extra workers past it only throttle.

## Known gaps

- A claim stays `extracted`, with its message in a DLQ, if the review request fails to send on
  every extraction delivery, or the DB or worker fails on the last review delivery. Needs a DLQ
  alarm or a stuck-claim check later.
- 12 turns × 120 s model timeout can exceed the 300 s visibility timeout: the request is delivered
  again while running. Safe (row lock, one proposal) but a second agent run.
- Quotable clauses are keyed by `clause_id` alone; a second binding document reusing ids would clash.

## Results

Manual run on 15 claims (D01–D06, D14, D17, D20, E01–E04, E06, E07): 14 with the right decision,
D17 rejected under 1.4 with `duplicate_of`. The miss: E02 approved under 4.1 without the 4.3
accessories cap. Approvals also cite general checks that passed (1.2, 1.3, 1.5).

## Testing

- **Unit:** quote and proposal rules, KB requests, prompt and claim data escaping, the agent loop
  with a scripted model (tools, corrections, limits, tool failures), SQS queue.
- **Integration:** review worker outcomes and concurrent deliveries, duplicate and training queries,
  review requests from the extraction worker.
- **Live** (`make test-live`, never in CI): D14 and D16 through the real model and KB → reject; both pass.

# T10 — MCP server for the agent's tools

**Goal:** the review agent's tools are available in Claude Code, to debug proposals.
**Out of scope:** changing the agent or its prompt (T11), fixing the bugs found here (Known gaps).

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| MCP server exposes the T09 tools; a tool change applies to agent and server together | `app/review/mcp_server.py` lists and calls `ReviewRun.tools()` itself | `tests/review/test_mcp_server.py` |
| Read-only access to data | The tools only read (KB `Retrieve`, `SELECT`s); the server's DB sessions are read-only (`postgresql_readonly`) | Manual: an `UPDATE` fails with `ReadOnlySqlTransaction` |
| Connected to Claude Code; README shows how | `larkfield-review` in `.mcp.json`; README "Review tools in Claude Code (MCP)" | Manual |
| Investigate a wrong proposal with the server | E02, see Results | Manual |
| Slash command for a repeated task | `/add-eval-case <doc_id>` (`.claude/skills/add-eval-case/`) | Manual: E01, E02 added |

## Design decisions

- **stdio, not HTTP.** Local debugging: Claude Code starts the server with `.env` and the AWS
  profile, no port to secure. *Rejected for now:* Streamable HTTP, needed only to share the server
  or run it in AWS, and then it needs auth.
- **The agent's tools, not a copy.** The server wraps `ReviewRun.tools()` (names, descriptions,
  schemas, code). *Rejected:* the agent using the server through `MCPClient`: the model would pass
  the claim id itself, and the per-run state (quotable clauses, cancel on failure) would need rewiring.
- **`claim_id` on the claim tools only** (`CLAIM_TOOLS` in `agent.py`: duplicates, training spend).
  The call loads the claim in any status (`load_claim_of_any_status`) and runs in a new `ReviewRun`,
  so a reviewed claim can be replayed. The policy tools run without a claim or database.
- **Tools run through Strands** (`stream`), as in the agent loop: Strands validates the arguments
  and catches errors. Invalid arguments → the validation message the agent gets; a failed lookup or
  error inside a tool → its exception type only, details in stderr.

Config: `DATABASE_URL`, `POLICY_KB_ID`, `AWS_REGION`, `AWS_PROFILE` from `.env`. New dependency `mcp`.

## Results

**E02** (EUR 8,655.70 of desk equipment) was approved; correct is **reject** under 4.3 and 7.1
(accessories up to EUR 50 per claim; its cables and adapters are EUR 480.40). With the server:
- 4.3 isn't in the proposal's `retrieved_clauses`; searching "accessories cables adapters" returns
  it first, so retrieval isn't the cause.
- The agent searched only for equipment and checked only per-item limits (pushed by IT4.2).

Later fix: search once per kind of item; compare per-claim limits with the sum of those items.
E02 (reject, `4.3`, `7.1`) and E01 (approve, `1.1`) are now review cases.

## Known gaps

- KB `references` come back JSON-quoted (`"\"2.2\""`), so `get_clause` on a reference copied as
  written finds nothing (`_chunk` in `app/review/policy.py`).
- The tools return current data, not what the agent saw: a later status change can affect the
  training total of `get_training_spend` tool.

## Testing

Unit tests run the server through the MCP SDK's in-memory client (tools match the agent's, results,
errors); an integration test loads a reviewed claim; E01 and E02 are pinned in
`tests/evals/test_review_cases.py`.

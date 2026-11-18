# Larkfield

Expense intake desk: an employee uploads a receipt with a business purpose, the system extracts its
fields, an AI agent proposes approve / reject / needs info citing the expense policy, and a finance
reviewer makes the final decision.

## Run locally

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up --build     # PostgreSQL + API on http://localhost:8000
curl localhost:8000/health    # {"status":"ok","database":"ok"}
```

Development:

```bash
uv sync
docker compose up -d db
make migrate                  # alembic upgrade head
uv run uvicorn app.main:app --reload
make check                    # lint, type check, tests (same as CI)
```

Configuration comes from environment variables; see [.env.example](.env.example).

## Review tools in Claude Code (MCP)

The review agent's tools (`search_policy`, `get_clause`, `find_duplicate_claims`,
`get_training_spend`) are served over MCP by [app/review/mcp_server.py](app/review/mcp_server.py),
so Claude Code can run them to debug a proposal. The server lists `ReviewRun.tools()` itself, so a
change to a tool changes it for the agent and the server together. The claim tools
(`find_duplicate_claims`, `get_training_spend`) take a `claim_id` and run as they would in a
review of that claim (in any status). The tools only read, and the server's database sessions are
read-only.

The server is registered in [.mcp.json](.mcp.json) and runs over stdio: Claude Code starts it as
a child process with the settings in `.env`:

```json
"larkfield-review": {
  "command": "uv",
  "args": ["run", "--env-file", ".env", "python", "-m", "app.review.mcp_server"]
}
```

1. `cp .env.example .env` and fill in `DATABASE_URL`, `POLICY_KB_ID`, `AWS_REGION` and `AWS_PROFILE`
   (the profile needs `bedrock:Retrieve` on the knowledge base).
2. `docker compose up -d db`.
3. Start Claude Code in the repo and approve `larkfield-review` when asked (or via `/mcp`).
   The tools appear as `mcp__larkfield-review__<tool>`.


## Why Python and FastAPI (vs Django)

**Python:** the AI tooling this project depends on is Python-first: boto3 for Bedrock, the
Strands Agents SDK, and the MCP SDK.

**FastAPI over Django:**
- The claim contracts (`ExtractedExpense`, `ReviewProposal`) are Pydantic models. FastAPI
  validates requests and responses with them directly. Django REST Framework would need serializers
  that repeat the same shapes.
- Django's strengths are its admin, templates, forms and ORM, and this project uses none of them:
  the UI is Next.js, auth is Cognito, and the database layer is SQLAlchemy + Alembic.
- It's async-native, so a request can wait on the database, S3 and Bedrock without blocking a worker.
- `Depends` makes it easy to swap the database or AWS for fakes, so unit tests stay offline.

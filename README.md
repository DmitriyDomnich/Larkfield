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
uv run uvicorn app.main:app --reload
make check                    # lint, type check, tests (same as CI)
```

Configuration comes from environment variables; see [.env.example](.env.example).

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

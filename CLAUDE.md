# Larkfield — expense intake desk

Employees upload receipts/invoices with a business purpose; the system extracts fields, an AI agent
proposes approve / reject / needs-info citing expense-policy clauses, a finance reviewer decides,
the employee is emailed. **The AI never makes the final decision.**

## Stack
- API: Python 3.13, FastAPI, SQLAlchemy 2.x (async, psycopg 3), Alembic, Pydantic v2 + pydantic-settings
- Tooling: uv, ruff, mypy (strict), pytest + coverage (≥ 80%), Docker Compose, GitHub Actions
- Bedrock (Converse, `eu.` inference profiles), Bedrock KB + S3 Vectors, Strands Agents, MCP,
  AWS (S3, SQS, ECS Fargate, RDS, Cognito, SES, Lambda), Next.js frontend

## Commands
```
make up          # API + PostgreSQL via docker compose (needs .env: cp .env.example .env)
make check       # lint + typecheck + all tests with coverage (needs db: docker compose up -d db)
make test-unit   # tests without a database
make fmt         # ruff fix + format
uv add <pkg>     # add dependency (never pip install; never edit uv.lock by hand)
```

## Layout — by feature
```
app/core/        shared: config.py (Settings), db.py (engine/session)
app/<feature>/   router.py, schemas.py, service.py, models.py — e.g. health, claims, review
tests/<feature>/ mirrors app/
specs/TNN-*.md   one spec per ticket, written before code
```
New feature = new package under `app/`, router registered in `app/main.py:create_app`.

## Conventions
- All config via `app.core.config.Settings` (env vars / `.env`). No secrets, URLs or keys in code,
  tests, compose or CI files. Add new settings to `.env.example` with a placeholder.
- Fully typed; mypy strict must pass. Pydantic models at API boundaries; don't return ORM objects.
- Routers stay thin; logic in `service.py`, injected via `Depends` so tests can override.
- Unit tests never call AWS or a real DB (use `dependency_overrides` / fakes). Tests needing
  PostgreSQL are marked `@pytest.mark.integration`.
- Every acceptance criterion in the ticket's spec has at least one test.
- Never put exception text, DSNs or stack traces in HTTP responses — log them.
- Async all the way: endpoints and services are `async def`, and the DB goes through `AsyncSession` (`Depends(get_session)`).
  Never call blocking code (boto3, `time.sleep`, sync file/HTTP I/O) inside `async def`. Wrap it in
  `asyncio.to_thread(...)` instead.
- No lazy loading in async SQLAlchemy (it raises `MissingGreenlet`): load relationships explicitly
  with `selectinload(...)`.
- The engine lives on `app.state` (created in `lifespan`). Never cache an `AsyncEngine` in a module global.
- Async tests are plain `async def test_...` (pytest-asyncio auto mode, no decorator needed).

## Git flow
`main` ← `dev` ← `feature/TNN-short-name`. One PR per ticket into `dev`, linking `specs/TNN-*.md`.
CI (lint, typecheck, test) must be green to merge.
**Never `git add`, commit, push or create branches — the developer does all git operations.**

## Hooks
`.claude/hooks/py-check.sh` runs after every Edit/Write of a `.py` file: ruff fix + format on the file,
then unit tests. If it reports a failure, fix it before doing anything else.

## Rules the agent keeps breaking
<!-- Add a rule here when the same mistake happens twice. -->

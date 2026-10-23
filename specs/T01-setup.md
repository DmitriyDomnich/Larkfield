# T01 — Project setup

**Goal:** every change is checked locally and on every pull request. **Out of scope:** deployment.

## Acceptance criteria

| Criterion | How | Tested by |
|---|---|---|
| Config from env, no secrets in repo | pydantic-settings; `DATABASE_URL` required; `.env` gitignored | `tests/core/test_config.py` |
| One command starts API + PostgreSQL | `docker compose up --build` | manual `curl /health` |
| `/health` reports DB reachability | `SELECT 1` with a 2s timeout | `tests/health/` |
| PRs run lint, type check, tests; failure blocks merge | `ci.yml` + branch ruleset on `main`/`dev` | PR with a failing test is blocked |
| README: run locally + why FastAPI | `README.md` | review |

## Design decisions

**Layout by feature** (`app/core/` + `app/<feature>/`). *Rejected: by layer* (`routers/`, `models/`,
`services/`), because tickets are split by feature, so one ticket's PR would touch every layer folder.

**Async SQLAlchemy + psycopg 3.** *Rejected: sync*, which is simpler today, but the agent (Strands async
API) and streaming to the reviewer UI fit async, and switching later means rewriting every query.

## What should `/health` report when the database is down, and who acts on it?

- `503 {"status":"error","database":"unreachable"}` within 2s. No error details in the body; they go
  to the logs.
- **Load balancer** (once deployed) stops routing traffic to the task.
- **Developer** gets a CloudWatch alarm and fixes the DB. The likely cause is RDS stopped to save credits.

## Test plan

- Unit: config from env / missing URL fails; `/health` 200 and 503 (exact body, failure logged); hung
  DB times out.
- Integration (real Postgres in CI): `/health` returns 200.
- Coverage ≥ 80% enforced in CI.

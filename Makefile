.PHONY: up down logs extraction-worker review-worker migrate revision lint fmt typecheck test test-unit check eval-docs eval-extraction eval-retrieval eval-review kb-build

up:          ## start backend + db
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api extraction-worker review-worker

extraction-worker:
	uv run python -m app.extraction

review-worker:
	uv run python -m app.review

migrate:
	uv run alembic upgrade head

revision:    ## e.g. make revision m="add users"
	uv run alembic revision --autogenerate -m "$(m)"

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test-unit:
	uv run pytest -m "not integration"

test-live:
	LIVE_BEDROCK=1 uv run pytest tests/extraction/test_extractor_live.py tests/review/test_agent_live.py -v

test:        ## all tests + coverage
	uv run pytest --cov --cov-report=term-missing

check: lint typecheck test

eval-docs:   ## (re)generate evals/documents from their labels, e.g. make eval-docs ids="D01 E06"
	uv run python -m evals.generator $(ids)

eval-extraction:
	uv run python -m evals.extraction $(ids)

eval-retrieval:
	uv run python -m evals.retrieval $(args)

eval-review: ## live run, e.g. args="--cases 5"; args="--results evals/reports/review-….json" scores a saved run
	uv run python -m evals.review $(args)

kb-build:
	uv run python -m evals.retrieval.clause_files

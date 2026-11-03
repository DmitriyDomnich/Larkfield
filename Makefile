.PHONY: up down logs migrate revision lint fmt typecheck test test-unit check eval-docs

up:          ## start backend + db
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

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

test:        ## all tests + coverage
	uv run pytest --cov --cov-report=term-missing

check: lint typecheck test

eval-docs:   ## (re)generate evals/documents from their labels, e.g. make eval-docs ids="D01 E06"
	uv run python -m evals.generator $(ids)

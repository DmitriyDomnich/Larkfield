.PHONY: up down logs lint fmt typecheck test test-unit check

up:          ## start backend + db
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

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

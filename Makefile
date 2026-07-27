# DOC_01 — developer entrypoints. Uses uv to manage the 3.11 virtualenv.
.PHONY: install db-up db-down migrate downgrade revision seed seed-clear seed-channels curate curation-status dev test e2e pilot-check lint format check all

install:        ## Create the venv and install runtime + dev deps
	uv sync --extra dev

db-up:          ## Start Postgres 16 + pgvector
	docker compose up -d db

db-down:        ## Stop the database (keeps the volume)
	docker compose down

migrate:        ## Apply migrations to head
	uv run alembic upgrade head

downgrade:      ## Roll back one migration
	uv run alembic downgrade -1

revision:       ## Autogenerate a migration: make revision m="message"
	uv run alembic revision --autogenerate -m "$(m)"

seed:           ## Idempotently load topics/prereqs/diagnostic bank (DOC_02 §3)
	uv run python -m app.seeds.loader seed

seed-clear:     ## Truncate catalog tables (dev only; blocked when ENV=study)
	uv run python -m app.seeds.loader clear

seed-channels:  ## Load + verify the YouTube channel allow-list (DOC_03 §3)
	uv run python -m app.modules.curation.cli seed-channels

curate:         ## Run the curation pipeline: make curate ARGS="--topic T0.1"
	uv run python -m app.modules.curation.cli curate $(ARGS)

curation-status: ## Print the coverage report grouped by tier
	uv run python -m app.modules.curation.cli status

dev:            ## Run the API with autoreload
	uv run uvicorn app.main:app --reload

test:           ## Run the test suite
	uv run pytest

e2e:            ## Run the end-to-end seam tests (DOC_09 §2)
	uv run pytest tests/e2e

pilot-check:    ## One-command pilot-readiness check (DOC_09 §3)
	uv run python -m scripts.validate

lint:           ## ruff check + mypy (DOC_01 §8.5)
	uv run ruff check .
	uv run mypy

format:         ## ruff format + import sort
	uv run ruff format .
	uv run ruff check --fix .

check: lint test ## Lint then test

all: migrate seed test lint ## DOC_02 done means: migrate seed test lint green

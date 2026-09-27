.PHONY: install run-llm run-backend run-frontend run-aimix migrate create-user \
        import-django-db lint format typecheck test check kill-back kill-front kill-all

UV ?= uv
NPM ?= npm
BACKEND := cd backend && $(UV) run

# Install all dependencies
install:
	$(UV) sync
	cd frontend && $(NPM) install

# --- Run ---------------------------------------------------------------------

# Run the FastAPI backend (auto-reloads on code changes)
run-backend:
	$(BACKEND) uvicorn api.main:create_app --factory --reload --port 8000

# Run the React Frontend
run-frontend:
	cd frontend && $(NPM) start

# Run backend + frontend concurrently
run-aimix:
	$(MAKE) -j 2 run-backend run-frontend

# Send one prompt to the configured LLM provider (credentials smoke test)
run-llm:
	$(BACKEND) python -m api.cli llm-probe --list-models

# --- Database ----------------------------------------------------------------

# Create or upgrade the database schema
migrate:
	$(BACKEND) alembic upgrade head

# Create an account: make create-user USERNAME=alice
create-user:
	$(BACKEND) python -m api.cli create-user $(USERNAME)

# One-off: copy accounts and pipelines from the old Django database
import-django-db:
	$(BACKEND) python -m api.cli import-django-db db.sqlite3

# --- Quality gates -----------------------------------------------------------

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy

test:
	$(UV) run pytest
	cd frontend && $(NPM) test

# Everything CI would run. The pytest suite also checks that the Alembic
# migrations build exactly the models' schema.
check: lint typecheck
	$(UV) run pytest
	cd frontend && $(NPM) test
	cd frontend && $(NPM) run build

# --- Stop --------------------------------------------------------------------

kill-back:
	-pkill -f "uvicorn api.main"
	@echo "Backend killed."

kill-front:
	-pkill -f "npm start"
	-pkill -f "vite"
	@echo "Frontend killed."

kill-all: kill-back kill-front
	@echo "All AIMIx processes have been terminated."

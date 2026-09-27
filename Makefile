.PHONY: install run-llm run-backend run-frontend run-aimix superuser migrate \
        lint format typecheck test check kill-back kill-front kill-all

UV ?= uv
NPM ?= npm
MANAGE := cd backend && $(UV) run python manage.py

# Install all dependencies
install:
	$(UV) sync
	cd frontend && $(NPM) install

# --- Run ---------------------------------------------------------------------

# Run the Django Backend
run-backend:
	$(MANAGE) runserver

# Run the React Frontend
run-frontend:
	cd frontend && $(NPM) start

# Run backend + frontend concurrently
run-aimix:
	$(MAKE) -j 2 run-backend run-frontend

# Send one prompt to the configured LLM provider (credentials smoke test)
run-llm:
	$(MANAGE) llm_probe --list-models

# --- Database ----------------------------------------------------------------

migrate:
	$(MANAGE) migrate

superuser:
	$(MANAGE) createsuperuser

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

# Everything CI would run
check: lint typecheck
	$(MANAGE) check
	$(UV) run pytest
	cd frontend && $(NPM) test
	cd frontend && $(NPM) run build

# --- Stop --------------------------------------------------------------------

kill-back:
	-pkill -f "manage.py runserver"
	@echo "Backend killed."

kill-front:
	-pkill -f "npm start"
	-pkill -f "vite"
	@echo "Frontend killed."

kill-all: kill-back kill-front
	@echo "All AIMIx processes have been terminated."

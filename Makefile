.PHONY: install run-llm run-backend run-frontend run-aimix superuser kill-back kill-front kill-all

UV ?= uv
NPM ?= npm

# Install all dependencies
install:
	$(UV) sync
	cd frontend && $(NPM) install

# Run the standalone LLM script
run-llm:
	$(UV) run backend/test_llm_standalone.py

# Run the Django Backend
run-backend:
	cd backend && PYTHONPATH=$(CURDIR) $(UV) run python manage.py runserver

# Run the Angular Frontend
run-frontend:
	cd frontend && $(NPM) start

# Run backend + frontend concurrently
run-aimix:
	$(MAKE) -j 2 run-backend run-frontend

# Create a superuser for authentication
superuser:
	cd backend && $(UV) run python manage.py createsuperuser

# Kill the Django Backend
kill-back:
	-pkill -f "manage.py runserver"
	@echo "Backend killed."

# Kill the Angular Frontend
kill-front:
	-pkill -f "npm start"
	-pkill -f "ng serve"
	@echo "Frontend killed."

# Kill all AIMIx processes
kill-all: kill-back kill-front
	@echo "All AIMIx processes have been terminated."

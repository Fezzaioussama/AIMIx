.PHONY: run-llm run-backend run-frontend run-all install

UV := /home/oussama/.local/bin/uv

# Install all dependencies
install:
	$(UV) sync
	cd frontend/AIMIx && npm install

# Run the standalone LLM script
run-llm:
	$(UV) run backend/main.py

# Run the Django Backend
run-backend:
	cd backend && PYTHONPATH=$(CURDIR) $(UV) run python manage.py runserver

# Run the Angular Frontend
run-frontend:
	cd frontend/AIMIx && npm start

# Run both concurrently
run-all:
	$(MAKE) -j 2 run-backend run-frontend

# Create a superuser for authentication
superuser:
	cd backend && $(UV) run python manage.py createsuperuser
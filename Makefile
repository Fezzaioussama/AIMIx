.PHONY: run-llm run-backend run-frontend run-n8n stop-n8n run-aimix install

UV ?= uv
NPM ?= npm
N8N_BIN := n8n-engine/node_modules/.bin/n8n

# Install all dependencies
install:
	$(UV) sync
	cd frontend && $(NPM) install
	cd n8n-engine && $(NPM) install

# Run the standalone LLM script
run-llm:
	$(UV) run backend/test_llm_standalone.py

# Run the Django Backend
run-backend:
	cd backend && PYTHONPATH=$(CURDIR) $(UV) run python manage.py runserver

# Run the Angular Frontend
run-frontend:
	cd frontend && $(NPM) start

$(N8N_BIN):
	cd n8n-engine && $(NPM) install

# Run n8n workflow engine
run-n8n: | $(N8N_BIN)
	N8N_USER_FOLDER=$(CURDIR)/n8n-data \
	N8N_SECURE_COOKIE=false \
	N8N_DISABLE_UI_SECURITY=true \
	$(NPM) --prefix n8n-engine start

# Run backend + frontend + n8n concurrently
run-aimix:
	$(MAKE) -j 3 run-backend run-frontend run-n8n

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

# Kill n8n workflow engine
kill-n8n:
	-pkill -f "n8n"
	@echo "n8n killed."

# Kill all AIMIx processes
kill-all: kill-back kill-front kill-n8n
	@echo "All AIMIx processes have been terminated."

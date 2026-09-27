# Getting started

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.10+ (pinned in `.python-version`) | Backend |
| [uv](https://docs.astral.sh/uv/) | recent | Python venv + dependency manager (`uv.lock`) |
| Node.js + npm | Node 20+ (tested on 24) | Frontend (Vite, React 19) |
| make | any | All commands are wrapped in the root `Makefile` |
| An LLM API key | — | OpenRouter (default) or TogetherAI |

## First-time setup

```bash
make install                           # uv sync  +  npm install in frontend/
cp backend/.env.example backend/.env   # then edit it (see below)
make migrate                           # create the schema (backend/aimix.sqlite3)
make run-llm                           # smoke test: prints the model list
```

### Minimum `.env` edits

Open `backend/.env` and set at least:

```dotenv
LLM_PROVIDER=openrouter          # or togetherai
OPEN_ROUTER_KEY=sk-or-...        # when LLM_PROVIDER=openrouter
TOGAI_API_KEY=...                # when LLM_PROVIDER=togetherai
```

Everything else has a working default for local development. Placeholder values
such as `your_api_key_here` or `change-me` are treated as **unset** by
`config/settings.py`, so a half-filled `.env` fails fast
with `provider_not_configured` instead of a confusing upstream 401.

The full variable list, with comments, is `backend/.env.example`. An existing
`.env` from the Django version keeps working: `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS` and the other `DJANGO_*` names are still read.

### Coming from the Django version

Your old data lives in `backend/db.sqlite3`. Copy it into the new database once:

```bash
make migrate
make import-django-db     # accounts (same passwords), pipelines and steps
```

The import keeps ids and refuses to run into a database that already has
accounts, so running it twice is harmless. `db.sqlite3` is only read.

## Running

```bash
make run-aimix        # backend :8000 and frontend :4200 in parallel
```

Open <http://localhost:4200>, register an account, sign in.

- The Vite dev server **proxies `/api` to `http://127.0.0.1:8000`**
  (`frontend/vite.config.ts`), so the browser sees one origin and no CORS setup
  is needed in development.
- Interactive API docs (Swagger UI): <http://127.0.0.1:8000/api/docs>.
- Create an account from the terminal with `make create-user USERNAME=alice`.
- Stop everything with `make kill-all`.

Run one side only with `make run-backend` or `make run-frontend`.

## Try each feature

1. **Chat** (`/chat`) — type a prompt; the reply streams token by token.
2. **Pipeline Builder** (`/pipeline`) — add steps, pick a model per step, write
   prompts using `{input}`, **Save**, then **Run** with an input.
3. **Auto Pipeline** (`/auto-pipeline`) — describe a workflow in plain language;
   a planner model returns steps you can edit and save.

## Talking to the API directly

```bash
# 1. get a token
curl -s -X POST localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"me","password":"secret-pass-123"}'

# 2. use it
TOKEN=...   # the "access" value from step 1
curl -s localhost:8000/api/models -H "Authorization: Bearer $TOKEN"
```

See [api-reference.md](api-reference.md) for every endpoint.

## Environments

`APP_ENV` selects the behaviour; everything else comes from the same variables.

| `APP_ENV` | Used by | Behaviour |
|---|---|---|
| `local` (default) | `make run-backend` | Throwaway `SECRET_KEY` allowed, `/api/docs` on |
| `test` | `pytest` (pinned in `tests/conftest.py`) | In-memory SQLite, no provider keys, fast hashing |
| `production` | your deployment | Refuses to start with `DEBUG=true`, no `SECRET_KEY`, or empty `ALLOWED_HOSTS`; HSTS on, `/api/docs` off |

In production run Uvicorn behind a TLS-terminating proxy that also redirects
HTTP to HTTPS, e.g. `uvicorn api.main:create_app --factory --proxy-headers`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `provider_not_configured` (503) | Key missing or still a placeholder | Set the key matching `LLM_PROVIDER` in `backend/.env`, restart the backend |
| `provider_unavailable` (502) | Provider rejected the call (bad key, unknown model, quota) | Run `make run-llm`, then `cd backend && uv run python -m api.cli llm-probe "hi"` to see the provider's message |
| `provider_timeout` (504) | Model slower than `LLM_TIMEOUT_SECONDS` | Raise it in `.env`, or pick a faster model |
| Redirected to `/login` unexpectedly | Access token expired (default 60 min); the client does not refresh it yet | Sign in again — see [known-issues.md](known-issues.md) |
| `no such table: users` / `pipelines` | Migrations not applied | `make migrate` |
| Frontend shows "Could not reach the server." | Backend not running on :8000 | `make run-backend` |
| Port already in use | A previous run is still alive | `make kill-all` |
| `validation_error` "Unknown model ..." | Model id not in the active provider's catalogue | Pick one from `GET /api/models`, or add it — see [llm-providers.md](llm-providers.md) |

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

### Chat's native pipeline tools

The chat agent always has three Python functions:

| Function | What it does |
|---|---|
| `list_pipelines()` | Lists your saved pipelines with ids, names, and step counts. |
| `inspect_pipeline(pipeline_id)` | Shows one of your pipelines, including its steps, prompts, and models. |
| `run_pipeline(pipeline_id, input_text)` | Runs one of your pipelines and returns its outputs and step results. |

These functions use the authenticated user's identity. The agent cannot inspect
or run another user's pipeline. Running a pipeline starts an agent for each step
and may take as long as a normal pipeline run. Chat history is not persisted.

### Give chat and pipeline steps MCP tools

Chat uses a LangGraph agent with the same `LLM_PROVIDER` and default model as
pipelines. Each pipeline step uses its selected model. Set `MCP_SERVERS` in
`backend/.env` to a JSON object. Every tool advertised by every configured
server is available to authenticated chat users and pipeline steps.
No server is configured by default. The connectors in a coding assistant or IDE
are separate and do not automatically become AIMIx server tools.

For example, this public server exposes LangChain documentation tools:

```dotenv
MCP_SERVERS='{"docs":{"transport":"streamable_http","url":"https://docs.langchain.com/mcp"}}'
```

A local open-source MCP server can use stdio. For example, the [MCP filesystem
server](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md)
requires Node.js and an explicit directory grant:

```dotenv
MCP_SERVERS='{"files":{"transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/absolute/allowed/path"]}}'
```

Put several named entries in the same JSON object to load all their tools.
HTTP entries may include a `headers` object; stdio entries may include `env`
for credentials. Keep secrets in the ignored `backend/.env`. Configure only
servers and filesystem paths that all authenticated AIMIx users may access; MCP server
credentials are shared by the backend. MCP discovery and calls have an explicit
`MCP_TIMEOUT_SECONDS` limit (30 seconds by default), and the full agent has
`AGENT_TIMEOUT_SECONDS` (one hour) and `AGENT_RECURSION_LIMIT` (25). There are
no automatic retries. The selected model must support tool calling.

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

1. **Chat** (`/chat`) — type a prompt; the LangGraph agent can use native pipeline functions and configured MCP tools.
2. **Pipeline Builder** (`/pipeline`) — use the workflow canvas to add parallel
   steps or insert a new stage, then edit each step in the sidebar. Mark every
   deliverable as **Output**, write prompts using `{input}`, **Save**, then **Run**
   with an input. Run results group deliverables by stage.
3. **Auto Pipeline** (`/auto-pipeline`) — describe a workflow in plain language;
   name the deliverables you want. Review the generated stages, add more outputs
   where needed, fill in their prompts, then save and open the builder.

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

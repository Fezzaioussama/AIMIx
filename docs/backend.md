# Backend reference

FastAPI + SQLAlchemy 2.0 + Alembic, served by Uvicorn and run with `uv`. The
import root is `backend/`: the top-level packages are `config`, `api`, `llm` and
`migrations`.

```
backend/
  alembic.ini               # Alembic config; the database URL comes from settings
  migrations/               # Alembic env + versions/
  config/                   # settings + logging, no business logic
  api/                      # the HTTP application
  llm/                      # provider layer, framework-agnostic
  tests/                    # pytest suite
```

Run it with `make run-backend`, which runs
`uvicorn api.main:create_app --factory --reload --port 8000` from `backend/`.
Outside production the interactive docs are at <http://127.0.0.1:8000/api/docs>.

## `config/` — settings and logging

`config/settings.py` defines one typed `Settings` class (pydantic-settings). It
reads the environment first, then `backend/.env`. `get_settings()` returns the
process-wide instance, and `pin_settings()` fixes it for tests and one-off tools.

| Setting | Variable (legacy name also accepted) | Default / meaning |
|---|---|---|
| `app_env` | `APP_ENV` | `local`, `production` or `test`. Production refuses `DEBUG=true`, an empty `SECRET_KEY` or empty `ALLOWED_HOSTS`, adds HSTS, and turns off `/api/docs` |
| `secret_key` | `SECRET_KEY` (`DJANGO_SECRET_KEY`) | Signs the JWTs. Outside production an empty value falls back to a throwaway key |
| `debug` | `DEBUG` (`DJANGO_DEBUG`) | FastAPI debug mode |
| `allowed_hosts` | `ALLOWED_HOSTS` (`DJANGO_ALLOWED_HOSTS`) | Comma-separated `Host` allowlist (`localhost,127.0.0.1`) |
| `cors_allowed_origins` | `CORS_ALLOWED_ORIGINS` (`DJANGO_CORS_ALLOWED_ORIGINS`) | Comma-separated origins (the Vite dev server) |
| `database_url` | `DATABASE_URL` | SQLAlchemy URL; default `backend/aimix.sqlite3` |
| `log_level` | `LOG_LEVEL` (`DJANGO_LOG_LEVEL`) | `INFO` |
| `jwt_access_minutes` / `jwt_refresh_days` | `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | 60 minutes / 1 day |
| `password_hash_iterations` | `PASSWORD_HASH_ITERATIONS` | 1,000,000 (Django's PBKDF2 default) |
| `llm_provider` | `LLM_PROVIDER` | `openrouter` (default) or `togetherai`; aliases accepted |
| `llm_timeout_seconds` | `LLM_TIMEOUT_SECONDS` | Per provider call; 3600 (one hour) |
| `agent_timeout_seconds` / `agent_recursion_limit` | `AGENT_TIMEOUT_SECONDS` / `AGENT_RECURSION_LIMIT` | Chat run limit (3600 seconds) / graph step limit (25) |
| `mcp_timeout_seconds` / `mcp_servers` | `MCP_TIMEOUT_SECONDS` / `MCP_SERVERS` | MCP call limit (30 seconds) / configured server JSON |
| `pipeline_max_parallel_steps` | `PIPELINE_MAX_PARALLEL_STEPS` | Provider calls one parallel stage makes at once (4) |
| `openrouter_api_key` / `togetherai_api_key` | `OPEN_ROUTER_KEY` (or `OPENROUTER_API_KEY`) / `TOGAI_API_KEY` | Credentials; placeholder values such as `your_api_key_here` count as unset |
| `openrouter_base_url` / `togetherai_base_url` | `OPENROUTER_BASE_URL` / `TOGETHERAI_BASE_URL` | Optional proxy/gateway override |
| `openrouter_default_model` / `togetherai_default_model` | `OPENROUTER_DEFAULT_MODEL` / `TOGETHERAI_DEFAULT_MODEL` | Default model id |

`llm_api_keys`, `llm_base_urls` and `llm_default_models` expose the provider
settings as dicts keyed by provider name. `config/logging_setup.py` configures
logging once, from the app factory.

## `api/` — the HTTP application

### `main.py` and `routes.py`

`create_app()` builds the app: it creates the `Database`, installs the error
handlers and middleware, and mounts `routes.api_router()` under `/api`.
`routes.py` is the routing table. Routers in `PUBLIC_ROUTERS` (register, login,
refresh) are open. Every router in `PROTECTED_ROUTERS` is mounted behind the
`current_user` dependency, so **new routes are authenticated by default**.

### `deps.py`

| Dependency | Gives the endpoint |
|---|---|
| `DbSession` | A SQLAlchemy `Session` for the request, closed afterwards |
| `AppSettings` | The `Settings` |
| `Signer` | A `TokenSigner` configured from the settings |
| `CurrentUser` | The `User` behind the bearer token, or a 401 `not_authenticated` |
| `Providers` | A factory for the configured `LLMProvider` used by pipelines |
| `Agents` | A factory for the LangGraph chat agent, called after request validation |

Tests replace any of these with `app.dependency_overrides`.

### `models.py` and `db.py`

| Model (table) | Fields | Invariants |
|---|---|---|
| `User` (`users`) | `username` (unique), `password_hash`, `created_at` | — |
| `Pipeline` (`pipelines`) | `name`, `user_id` (FK, cascade), `created_at` | `steps` load ordered by `(stage, order)` |
| `PipelineStep` (`pipeline_steps`) | `pipeline_id` (FK, cascade), `order`, `stage`, `title`, `is_output`, `prompt`, `model` | **unique `(pipeline_id, order)`** |

`PipelineStep.model` is a plain string column; the request schemas check it
against the catalogue. `db.Database` owns the engine and session factory. SQLite
connections are allowed across threads (endpoints run in a threadpool) and have
foreign keys switched on; `sqlite://` uses one shared in-memory connection.

### `endpoints/` and `schemas/`

| Endpoint module | Routes | Schemas (`api/schemas/`) |
|---|---|---|
| `auth.py` | `POST /register`, `POST /login`, `POST /token/refresh` (public); `GET /protected` | `auth.py`: `RegisterRequest`, `LoginRequest`, `TokenPairResponse`, `RefreshRequest`, `AccessTokenResponse`, `WhoAmIResponse` |
| `chat.py` | `POST /chat` (streams `text/plain`) | `chat.py`: `ChatRequest` (non-blank `prompt`) |
| `models.py` | `GET /models` | `pipelines.py`: `ModelsResponse` |
| `pipelines.py` | list/create, get/put/patch/delete, `run`, `generate` | `pipelines.py`: `PipelineIn`, `PipelinePatch`, `PipelineOut`, `RunRequest`, `RunResponse`, `GenerateRequest`, `GenerateResponse` |

`schemas/common.py` holds the shared field types: `NonBlank` (trimmed, not
empty) and `ModelId` (must be in the active catalogue). A step without `stage`
gets `stage = order`. A pipeline needs at least one step, and step orders must
be unique.

### `repositories/`

| Module | Functions |
|---|---|
| `pipelines.py` | `for_user` (newest first, steps loaded), `get_owned` (or `NotFound`), `create_with_steps`, `replace_steps` (rename and/or replace every step in one transaction), `delete` |
| `users.py` | `get`, `get_by_username`, `create` |
| `legacy_import.py` | `import_django_database` — the one-off copy from the old Django SQLite file |

Each write commits its own transaction.

### `services/`

| Module | Responsibility |
|---|---|
| `pipelines.py` | `run` (stages in order, parallel steps in a thread pool, returns `RunResult`), `generate` + `parse_plan` (planner), `ensure_runnable`, `output_orders`. Logs `pipeline.run` with id, stage and step counts, duration. |
| `prompts.py` | `step_prompt`, `merge_stage_outputs`, `pipeline_generation_prompt`. |
| `chat.py` | `stream_reply` — eager first chunk, then an async generator that logs mid-stream failures. |
| `agent.py` | Builds the LangGraph agent, combines native and MCP tools, and streams assistant text. |
| `agent_tools.py` | Authenticated `list_pipelines`, `inspect_pipeline`, and `run_pipeline` functions. Each call opens its own session and uses the ownership-scoped repository. |
| `mcp.py` | Converts validated HTTP or stdio MCP server settings into bounded adapter connections. |
| `accounts.py` | `register` (password policy, unique username), `sign_in` → `TokenPair`, `refresh_access`, `authenticate`. |
| `password_policy.py` | The four rules Django applied: similarity to the username, minimum length 8, Django's common-password list (`api/data/common-passwords.txt.gz`), entirely numeric. |
| `llm.py` | **The only reader of provider settings.** `provider_config()`, `get_provider()` and `get_agent_model()`. |
| `catalog.py` | `available_model_ids()` (default first) and `default_model_id()` for the active provider. |
| `errors.py` | `PROVIDER_ERROR_MAP` and `as_domain_error()` — the one translation from `llm` errors to domain errors. |

### `security.py`

Pure functions with no web framework. `hash_password` / `verify_password` use
Django's `pbkdf2_sha256$<iterations>$<salt>$<hash>` format, so accounts imported
from the old backend keep their passwords. `TokenSigner` issues and reads HS256
JWTs with `token_type` (`access` or `refresh`) and `user_id` claims.

### `exceptions.py`, `errors.py` and `middleware.py`

`DomainError(detail)` carries a class-level `code`, `status_code` and optional
`headers`. The subclasses are `ValidationFailed` (400), `NotAuthenticated` (401,
`WWW-Authenticate: Bearer`), `NotFound` (404), `ProviderNotConfigured` (503),
`ProviderUnavailable` (502), `ToolUnavailable` (502), `ProviderTimedOut` (504) and
`UpstreamResponseInvalid` (502).

`errors.install_error_handlers` renders:
- `DomainError` as its own code and status.
- Request validation errors as 400 `validation_error`, one `field: message` per problem.
- Framework HTTP errors (404, 405, …) by status via `STATUS_CODES`.
- Anything unexpected as 500 `server_error`.

`middleware.py` adds the `Host` allowlist, CORS, and security headers
(`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
`Cross-Origin-Opener-Policy`, plus HSTS in production).

### `cli.py`

```bash
cd backend
uv run python -m api.cli llm-probe --list-models     # what `make run-llm` does
uv run python -m api.cli llm-probe "Say hi"          # one real call, default model
uv run python -m api.cli llm-probe "Say hi" --model openai/gpt-oss-120b
uv run python -m api.cli create-user alice            # asks for the password
uv run python -m api.cli import-django-db db.sqlite3  # one-off, into an empty database
```

## `migrations/` — Alembic

`env.py` takes the URL from `config.settings` (or from the `sqlalchemy.url`
option, which the tests use) and runs in batch mode, so SQLite can `ALTER`.

```bash
cd backend
uv run alembic upgrade head                                   # make migrate
uv run alembic revision --autogenerate -m "add pipeline tags"  # after changing models.py
```

Review every autogenerated revision before committing it.
`test_database.py::test_migrations_build_exactly_the_models_schema` fails when
the models and the migrations disagree.

## `llm/` — provider layer

Covered in [llm-providers.md](llm-providers.md).

## `tests/`

pytest with FastAPI's `TestClient`. `conftest.py` pins `TEST_SETTINGS` before any
app is built: in-memory SQLite, one hashing iteration, and **empty provider keys**,
so tests can never reach a real LLM.

| Fixture / helper | Use |
|---|---|
| `app`, `session` | A fresh app over a fresh in-memory database, and a session on it |
| `client`, `auth_client` | A `TestClient`, and one that sends a valid bearer token |
| `user`, `password`, `bearer(user)` | A saved account, its password, and an auth header |
| `FakeProvider`, `FailingProvider(error)` | Canned replies / a chosen `LLMError` |
| `fake_provider`, `use_provider(app, provider)` | Override the pipeline provider dependency |
| `FakeAgent`, `use_agent(app, agent)` | Override the chat agent dependency |
| `default_model` | The active default model id |

| Test module | Covers |
|---|---|
| `test_endpoints.py` | HTTP behaviour: every non-public route needs auth, auth flows, CRUD, run, generate, chat |
| `test_errors.py` | The error shape for 400/401/404/405/500 |
| `test_schemas.py` | Model-id validation, stages, required steps, non-blank fields |
| `test_security.py` | Django-compatible hashes (checked against a hash Django produced), password policy, tokens |
| `test_database.py` | Migrations match the models; the Django import |
| `test_pipeline_service.py` | `run`, parallel stages, outputs, `parse_plan`, prompts |
| `test_llm_providers.py` / `test_llm_catalog.py` | Provider adapter, registry, catalogue |
| `test_chat_agent.py` | MCP settings, discovery, streaming and failure mapping |
| `test_agent_tools.py` | Native pipeline functions, ownership, and chat tool invocation |
| `test_settings_and_config.py` | Settings parsing, legacy names, production guards |

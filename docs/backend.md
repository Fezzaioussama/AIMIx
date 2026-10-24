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
| `secret_key` | `SECRET_KEY` (`DJANGO_SECRET_KEY`) | Signs the JWTs and encrypts saved API keys. Outside production an empty value falls back to a throwaway key |
| `debug` | `DEBUG` (`DJANGO_DEBUG`) | FastAPI debug mode |
| `allowed_hosts` | `ALLOWED_HOSTS` (`DJANGO_ALLOWED_HOSTS`) | Comma-separated `Host` allowlist (`localhost,127.0.0.1`) |
| `cors_allowed_origins` | `CORS_ALLOWED_ORIGINS` (`DJANGO_CORS_ALLOWED_ORIGINS`) | Comma-separated origins (the Vite dev server) |
| `database_url` | `DATABASE_URL` | SQLAlchemy URL; default `backend/aimix.sqlite3` |
| `log_level` | `LOG_LEVEL` (`DJANGO_LOG_LEVEL`) | `INFO` |
| `frontend_dist_dir` | `FRONTEND_DIST_DIR` | Built React app to serve next to `/api` (the image sets it); empty serves none |
| `jwt_access_minutes` / `jwt_refresh_days` | `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | 60 minutes / 1 day |
| auth controls | `ALLOW_PUBLIC_REGISTRATION`, `AUTH_RATE_LIMIT_REQUESTS`, `AUTH_RATE_LIMIT_WINDOW_SECONDS`, `REFRESH_COOKIE_NAME` | Public registration is off by default; auth operations are database-throttled; refresh tokens use a rotating HttpOnly cookie |
| `password_hash_iterations` | `PASSWORD_HASH_ITERATIONS` | 1,000,000 (Django's PBKDF2 default) |
| `llm_provider` | `LLM_PROVIDER` | `openrouter` (default) or `togetherai`; aliases accepted |
| `llm_timeout_seconds` | `LLM_TIMEOUT_SECONDS` | Per provider call; 3600 (one hour) |
| `agent_timeout_seconds` / `agent_recursion_limit` | `AGENT_TIMEOUT_SECONDS` / `AGENT_RECURSION_LIMIT` | Per chat or pipeline step agent limit (3600 seconds) / graph step limit (25) |
| `agent_tool_description_max_chars` | `AGENT_TOOL_DESCRIPTION_MAX_CHARS` | Maximum tool description length in the catalogue and planner prompt (300) |
| `mcp_timeout_seconds` / `mcp_servers` | `MCP_TIMEOUT_SECONDS` / `MCP_SERVERS` | MCP call limit (30 seconds) / configured server JSON |
| `workspace_dir` | `AGENT_WORKSPACE_DIR` | Sandboxed agent file root (`backend/workspace`) |
| workspace/network policy | `AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS` | `false`: workspace readers and outbound web tools cannot be offered together; explicit opt-in required |
| workspace limits | `WORKSPACE_MAX_FILE_BYTES`, `WORKSPACE_MAX_OUTPUT_CHARS`, `WORKSPACE_SEARCH_MAX_FILES`, `WORKSPACE_SEARCH_MAX_RESULTS`, `WORKSPACE_CSV_MAX_ROWS` | Bound local reads, searches, output, and CSV rows |
| `pipeline_max_parallel_steps` | `PIPELINE_MAX_PARALLEL_STEPS` | Agent steps that can run at once in one stage (4) |
| `run_max_concurrent` / `run_shutdown_grace_seconds` | `RUN_MAX_CONCURRENT` / `RUN_SHUTDOWN_GRACE_SECONDS` | Background runs executing at once in the process; the rest wait queued (4) / how long active runs get on shutdown to record that they were interrupted (5 seconds) |
| document limits | `DOCUMENT_MAX_BYTES`, `DOCUMENT_MAX_CHARS`, `DOCUMENT_MAX_PAGES`, `DOCUMENT_MAX_UNPACKED_BYTES` | Bound one uploaded document: its size (10 MB), the text kept (120,000 characters), PDF pages read (300) and what a `.docx` may unpack to (50 MB). `max_request_bytes` is `DOCUMENT_MAX_BYTES` plus 1 MB of multipart overhead |
| `openrouter_api_key` / `togetherai_api_key` | `OPEN_ROUTER_KEY` (or `OPENROUTER_API_KEY`) / `TOGAI_API_KEY` | Credentials; placeholder values such as `your_api_key_here` count as unset |
| `openrouter_base_url` / `togetherai_base_url` | `OPENROUTER_BASE_URL` / `TOGETHERAI_BASE_URL` | Optional proxy/gateway override |
| `openrouter_default_model` / `togetherai_default_model` | `OPENROUTER_DEFAULT_MODEL` / `TOGETHERAI_DEFAULT_MODEL` | Default model id |

`llm_api_keys`, `llm_base_urls` and `llm_default_models` expose the provider
settings as dicts keyed by provider name. The provider, keys and default models
are server-wide defaults: each user can override them on the Settings page
(`services/llm_settings.py`). `config/logging_setup.py` configures
logging once, from the app factory.

## `api/` — the HTTP application

### `main.py` and `routes.py`

`create_app()` builds the app: it creates the `Database` and the background
run executor (`app.state.run_executor`, a `BackgroundRunExecutor` whose thread
starts with the first run), installs the error handlers and middleware, and
mounts `routes.api_router()` under `/api`. Its `lifespan` marks runs a previous
process left active as interrupted on startup
(`services/runs.interrupt_abandoned_runs`) and shuts the executor down on exit.
`routes.py` is the routing table. Routers in `PUBLIC_ROUTERS` (register, login,
refresh/logout, health) are open; auth operations are rate-limited and registration
can be disabled. When `FRONTEND_DIST_DIR` is set, `frontend.py` then
serves the built app at `/` with an `index.html` fallback for client routes;
unknown `/api/...` paths stay a JSON `404`. Every router in `PROTECTED_ROUTERS` is mounted behind the
`current_user` dependency, so **new routes are authenticated by default**.

### `deps.py`

| Dependency | Gives the endpoint |
|---|---|
| `DbSession` | A SQLAlchemy `Session` for the request, closed afterwards |
| `AppSettings` | The `Settings` |
| `Signer` | A `TokenSigner` configured from the settings |
| `CurrentUser` | The `User` behind the bearer token, or a 401 `not_authenticated` |
| `Secrets` | A `SecretBox` keyed from the settings, for saved API keys |
| `Profile` | The user's `LLMProfile`: provider, default model and saved key (Settings page, else `.env`) |
| `Providers` | A factory for the user's `LLMProvider`, used by planning |
| `PipelineAgents` / `PipelineRun` | User-bound pipeline agent factory / run context (user, session, agents, run service) |
| `Executor` / `Runs` | The run executor (`app.state.run_executor`; tests swap in an inline one by overriding `run_executor`) / a `RunService` over it |
| `ToolCatalog` | User-bound native and MCP tool discovery for the builder and planner |
| `Agents` | A factory for the LangGraph chat agent, called after request validation |

Tests replace any of these with `app.dependency_overrides`.

### `models.py` and `db.py`

| Model (table) | Fields | Invariants |
|---|---|---|
| `User` (`users`) | `username` (unique), `password_hash`, `created_at`, `llm_provider` (null = `LLM_PROVIDER`) | — |
| `ProviderSetting` (`provider_settings`) | `user_id` (FK, cascade), `provider`, `api_key_encrypted`, `api_key_hint`, `default_model` | **unique `(user_id, provider)`**; `""` means not saved |
| `Pipeline` (`pipelines`) | `name`, `user_id` (FK, cascade), `created_at`, `inputs` | `steps` load ordered by `(stage, order)` |
| `PipelineStep` (`pipeline_steps`) | `pipeline_id` (FK, cascade), `order`, `stage`, `title`, `role`, `allowed_tools`, `is_output`, `expected_output`, `prompt`, `model` | **unique `(pipeline_id, order)`** |
| `Run` (`runs`) | `user_id` (FK, cascade), `pipeline_id` (FK, **set null** when the pipeline is deleted), `pipeline_name`, `definition` (JSON snapshot of the pipeline it runs), `input_text`, `input_values`, `status`, `final_output`, `error_code`, `error_detail`, `created_at`, `started_at`, `finished_at` | `status` is a `RunStatus`; `""` error fields mean none; `steps` load ordered by `(stage, step_order)` |
| `RunStep` (`run_steps`) | `run_id` (FK, cascade), `step_order`, `stage`, `title`, `model`, `status`, `is_output`, `input_used`, `output`, `tool_calls` (`[{"name","status"}]`), `error_code`, `error_detail`, `started_at`, `finished_at` | **unique `(run_id, step_order)`**; `status` is a `StepStatus` |

The run statuses live in one place, `models.py`: `RunStatus` (`queued`,
`running`, `succeeded`, `failed`, `cancelled`, `interrupted`), `StepStatus`
(`pending`, `running`, `succeeded`, `failed`, `cancelled`), and the sets
`ACTIVE_RUN_STATUSES` (queued, running) and `RESUMABLE_RUN_STATUSES` (failed,
cancelled, interrupted). They are stored as their lowercase value in a
`VARCHAR(16)` and read back as the enum.

`PipelineStep.model` is a plain string column; the request schemas check it
against the catalogue. `role` defaults to `""`; `allowed_tools` is JSON with
`null` for all tools, `[]` for none, or exact tool names. The migration gives
existing steps the original all-tools behavior. `Pipeline.inputs` is a JSON
list of `{"name", "label", "description"}` objects — the named run inputs —
and `expected_output` a step's deliverable (≤ 500 characters); existing rows
get `[]` and `""`. The naming rule and limits for inputs are constants in
`models.py` (`PIPELINE_INPUT_*`, `RESERVED_INPUT_NAME`). `db.Database` owns the engine
and session factory. SQLite connections are allowed across threads (endpoints
run in a threadpool) and have foreign keys switched on; `sqlite://` uses one
shared in-memory connection.

### `endpoints/` and `schemas/`

| Endpoint module | Routes | Schemas (`api/schemas/`) |
|---|---|---|
| `auth.py` | `POST /register`, `POST /login`, `POST /token/refresh` (public); `GET /protected` | `auth.py`: `RegisterRequest`, `LoginRequest`, `TokenPairResponse`, `RefreshRequest`, `AccessTokenResponse`, `WhoAmIResponse` |
| `chat.py` | `POST /chat` (streams `text/plain`) | `chat.py`: `ChatRequest` (non-blank `prompt`) |
| `health.py` | `GET /health` (public — the platform's health check) | `health.py`: `HealthResponse` |
| `models.py` | `GET /models` | `pipelines.py`: `ModelsResponse` |
| `llm_settings.py` | `GET`/`PUT /llm-settings`, `DELETE /llm-settings/keys/{provider}` | `llm_settings.py`: `LLMSettingsIn`, `ProviderSettingsIn`, `LLMSettingsOut`, `ProviderSettingsOut` |
| `agent_tools.py` | `GET /agent-tools` | `agent_tools.py`: `ToolDescriptorOut` (`name`, `description`, `source`) |
| `pipelines.py` | list/create, get/put/patch/delete, `run` (waits for a recorded run; kept for compatibility), `generate` | `pipelines.py`: `PipelineIn`, `PipelinePatch`, `PipelineOut`, `RunRequest`, `RunResponse`, `GenerateRequest`, `GenerateResponse` |
| `runs.py` | `POST /pipelines/{id}/runs` (202), `GET /runs` (paged), `GET /runs/{id}`, `POST /runs/{id}/cancel`, `POST /runs/{id}/resume`, `DELETE /runs/{id}` | `runs.py`: `RunListQuery`, `RunOut`, `RunSummaryOut`, `RunStepOut`, `RunDefinitionOut`, `RunPageOut` (+ `RunRequest` for the body) |

`schemas/common.py` holds the shared field types: `NonBlank` (trimmed, not
empty), `ModelId` (must be in some provider's catalogue), `ProviderName` and
`UtcDateTime` (a stored timestamp sent with its UTC offset). A step without `stage`
gets `stage = order`. A pipeline needs at least one step, and step orders must
be unique. Step `role` is optional (up to 100 characters); `allowed_tools` is
optional and, when explicit, contains unique, non-blank names. Tool availability
is checked when the agent runs. `PipelineInputField` validates each named
input through `services/pipeline_inputs.input_name_error`, the rule the planner
also applies; `RunRequest` only trims `input` and `inputs`, because which one a
run needs depends on the pipeline.

### `repositories/`

| Module | Functions |
|---|---|
| `pipelines.py` | `for_user` (newest first, steps loaded), `get_owned` (or `NotFound`), `create_with_steps`, `replace_steps` (rename, redeclare the inputs and/or replace every step in one transaction), `delete`. Writes take a `PipelineChanges` value whose `None` fields are kept. |
| `runs.py` | `create` (run + its step rows), `get_owned` (or `NotFound`), `load`, `page_for_user` (newest first, summary columns only, total), and the compare-and-set writes `set_status`, `set_step`, `end` (final status + settling running steps), `reopen` (resume), plus `delete` and `interrupt_active` (startup recovery; a database without the runs table has none) |
| `users.py` | `get`, `get_by_username`, `create` |
| `provider_settings.py` | `for_user`, `get`, `save` (active provider + per-provider upsert in one transaction), `clear_key` (idempotent) |
| `legacy_import.py` | `import_django_database` — the one-off copy from the old Django SQLite file |

Each write commits its own transaction.

### `services/`

| Module | Responsibility |
|---|---|
| `pipelines.py` | `prepare_run` (no steps → 400, snapshot through `multiagent/mapper.py`, bind the run's inputs — before anything is saved), `run` (in-process and unrecorded, for tests and one-off tools), and `generate` + `parse_plan` (tool-aware planner that also sanitises inputs and expected outputs). |
| `runs.py` | `RunService`: `start` (save the run queued, hand it to the executor), `run_to_end` / `run_saved_to_end` (start and wait: the compatibility endpoint and the chat tool), `resume`, `cancel`, `delete` (409 `Conflict` while active), and the job `_execute` (one attempt on the executor's loop, recording `succeeded`, `failed` or `interrupted`). `launcher()` binds it to one user for the chat agent; `interrupt_abandoned_runs()` runs at startup. Logs `run.cancelled`, `run.resumed`, `run.interrupted_on_startup` — never inputs or outputs. |
| `run_executor.py` | `RunExecutor` port (`submit(key, job) -> Future`, `cancel(key)`, `shutdown()`) and `BackgroundRunExecutor`: one asyncio loop on a daemon thread, started by the first job, at most `RUN_MAX_CONCURRENT` jobs at once. |
| `run_recorder.py` | `RunRecorder`, the `StepObserver` that writes each step event in its own short transaction (`STEP_CHANGES` registry: event kind → expected statuses + columns), and the run's `begin` / `end` with the endings `succeeded`, `failed`, `interrupted`, `cancelled`. Logs `run.started` and `run.finished` with status and duration. |
| `documents/` | Turns an uploaded file into run-input text. `extraction.py` (`extract_document`: picks a reader by extension, enforces size, tidies and truncates), `readers.py` (the `READERS` registry: PDF via pypdf, Word via python-docx, HTML via `toolbox/html_text.py`, plain text; every parser runs inside `_guarded`, which re-raises anything it throws as `DocumentUnreadable`), and `contracts.py` (`ExtractionLimits`, `ReadResult`, `ExtractedDocument`). Stateless: nothing is stored. A new format is one reader and one registry entry. |
| `pipeline_inputs.py` | Named run inputs: `input_name_error` (the naming rule) and `bind_run_inputs`, which checks a run's text or values against the declared inputs and builds the first stage's input — before any agent starts. |
| `multiagent/contracts.py` | Immutable `PipelineSpec` / `StepSpec` / `InputField` snapshots, `RunInputs`, run-result data, the async `StepAgent` protocol, and the observer port: `StepEventKind` (started, succeeded, failed, cancelled), `StepEvent`, `StepObserver`, `SILENT_OBSERVER` and `RunControl` (observer + results already completed). |
| `multiagent/mapper.py` | Copies loaded ORM pipeline and step fields into graph contracts before concurrent execution; `spec_to_json` / `spec_from_json` store a run's snapshot. |
| `multiagent/graph.py` | LangGraph `StateGraph`: one agent node per saved step, concurrent nodes within a stage, a barrier/join before the next stage, and result ordering by saved step order. Each node reports its step to the run's observer, and returns a completed step's saved result without running its agent (resume). `output_orders` decides which steps are outputs. The concurrency cap comes from `PIPELINE_MAX_PARALLEL_STEPS`; this module logs `pipeline.run`. |
| `multiagent/step_agent.py` | User-bound LangGraph step agent: selected model, role, native/MCP tools, final text, and tool call metadata. |
| `prompts.py` | `step_prompt` (fills `{input}` and `{name}` in one pass), `merge_stage_outputs`, `merge_input_values`, `pipeline_generation_prompt`, `step_agent_system_prompt` (role, expected output, tool guidance). |
| `chat.py` | `stream_reply` — eager first chunk, then an async generator that logs mid-stream failures. |
| `agent.py` | Builds and streams the chat-only LangGraph agent. |
| `agent_runtime.py` | Shared chat/pipeline tool policy, limits, and third-party failure translation. |
| `agent_types.py` | Immutable step task, agent outcome, tool descriptor, and tool call trace. |
| `agent_tools.py` | Authenticated `list_pipelines`, `inspect_pipeline`, and `run_pipeline` functions. Each call opens its own session and uses the ownership-scoped repository; `run_pipeline` goes through the run service (`PipelineLauncher`), so chat runs are recorded. `native_tools` adds the built-in toolbox. |
| `toolbox/` | Built-in agent tools: `registry.py` (name → builder, filtered by `AGENT_BUILTIN_TOOLS`), `tools.py` (LangChain adapters), `web.py` (Tavily search and SSRF-guarded fetch), `workspace.py` (sandboxed local text, CSV and artifacts), `calculator.py`, `html_text.py`, and `config.py`. See [architecture.md](architecture.md#built-in-tools). |
| `mcp.py` | Converts validated HTTP or stdio MCP server settings into bounded adapter connections. |
| `tool_catalog.py` | Discovers native read tools and configured MCP tools for `GET /agent-tools` and the planner. |
| `pipeline_agents.py` | Compatibility re-export of `multiagent.step_agent.PipelineAgentGenerator`. |
| `accounts.py` | `register` (password policy, unique username), `sign_in` → `TokenPair`, `refresh_access`, `authenticate`. |
| `password_policy.py` | The four rules Django applied: similarity to the username, minimum length 8, Django's common-password list (`api/data/common-passwords.txt.gz`), entirely numeric. |
| `llm.py` | **The only reader of provider credentials and transport settings.** `LLMProfile`, `provider_config(profile)`, `get_provider(profile)` and `get_agent_model(profile, model_id)`. A saved key wins over the `.env` one. |
| `llm_settings.py` | The Settings page: `resolve_profile()` (per request), `read()`, `save()`, `remove_key()`, and `environment_profile()` for the CLI. Keys are sealed with `SecretBox` and only their hint is returned. |
| `catalog.py` | `available_model_ids()` (default first), `default_model_id()` and `known_model_ids()`, for a given provider or `LLM_PROVIDER`. |
| `errors.py` | `PROVIDER_ERROR_MAP` and `as_domain_error()` — the one translation from `llm` errors to domain errors. |

### `security.py`

Pure functions with no web framework. `hash_password` / `verify_password` use
Django's `pbkdf2_sha256$<iterations>$<salt>$<hash>` format, so accounts imported
from the old backend keep their passwords. `TokenSigner` issues and reads HS256
JWTs with `token_type` (`access` or `refresh`) and `user_id` claims.
`SecretBox` encrypts saved API keys with Fernet, keyed by HKDF over
`SECRET_KEY`; a key sealed under another `SECRET_KEY` raises `UnreadableSecret`.

### `exceptions.py`, `errors.py` and `middleware.py`

`DomainError(detail)` carries a class-level `code`, `status_code` and optional
`headers`. The subclasses are `ValidationFailed` (400), `NotAuthenticated` (401,
`WWW-Authenticate: Bearer`), `NotFound` (404), `Conflict` (409, e.g. deleting a
run in progress), `ProviderNotConfigured` (503),
`ProviderUnavailable` (502), `ToolUnavailable` (502), `ProviderTimedOut` (504),
`UpstreamResponseInvalid` (502), and for documents `DocumentTooLarge` (413),
`UnsupportedDocument` (415) and `DocumentUnreadable` (422).

`errors.install_error_handlers` renders:
- `DomainError` as its own code and status.
- Request validation errors as 400 `validation_error`, one `field: message` per problem.
- Framework HTTP errors (404, 405, …) by status via `STATUS_CODES`.
- Anything unexpected as 500 `server_error`.

`middleware.py` adds `RequestSizeLimitMiddleware` (answers 413 `request_too_large`
to a body whose declared `Content-Length` exceeds `max_request_bytes`, before any
of it is read), the `Host` allowlist, CORS, and security headers
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
| `fake_provider`, `use_provider(app, provider)` | Override the planner's provider dependency |
| `use_pipeline_generator(app, generator)` | Override the pipeline step agent dependency |
| `InlineRunExecutor`, `use_inline_runs(app)` | Runs execute to their end inside the request; the `app` fixture installs it, so API tests see finished runs. `test_runs_service.py` uses the real background executor over a file database |
| `FakeAgent`, `use_agent(app, agent)` | Override the chat agent dependency |
| `default_model` | The active default model id |

| Test module | Covers |
|---|---|
| `test_endpoints.py` | HTTP behaviour: every non-public route needs auth, auth flows, CRUD, run, generate, chat |
| `test_errors.py` | The error shape for 400/401/404/405/500 |
| `test_schemas.py` | Model-id validation, stages, required steps, non-blank fields |
| `test_security.py` | Django-compatible hashes (checked against a hash Django produced), password policy, tokens |
| `test_database.py` | Migrations match the models and keep existing pipelines and steps; the Django import |
| `test_pipeline_service.py` | `run`, parallel stages, outputs, `parse_plan`, prompts |
| `test_pipeline_inputs.py` | Named run inputs and expected outputs: binding, placeholder filling, planner sanitising, and the HTTP contract |
| `test_multiagent_graph.py` | LangGraph stage barriers, bounded concurrency, result ordering, failure propagation, step events, reuse of completed steps, snapshot round trip |
| `test_runs_service.py` | Background runs end to end: recording, failure (and the cancelled parallel sibling), crashes, stop while running or queued, the concurrency limit, resume after failure (with the run's own snapshot), restart recovery, shutdown, delete |
| `test_runs_api.py` | The runs HTTP surface: 202 start and polling, validation before saving, resume, idempotent stop, 409 delete, paging and filtering, ownership, the recorded compatibility endpoint, a run outliving its pipeline |
| `test_llm_providers.py` / `test_llm_catalog.py` | Provider adapter, registry, catalogue |
| `test_chat_agent.py` | MCP settings, discovery, streaming and failure mapping |
| `test_pipeline_agents.py` | Step model selection, MCP tool calls, and discovery failures |
| `test_agent_tools.py` | Native pipeline functions, ownership, and chat tool invocation |
| `test_toolbox.py` / `test_web_tools.py` | Built-in tools: calculator safety, HTML text, registry, search, SSRF guard, size caps, and a run that survives a failing tool |
| `test_settings_and_config.py` | Settings parsing, legacy names, production guards |

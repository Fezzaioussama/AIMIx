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
| `llm_max_retries` / `llm_retry_base_delay_seconds` / `llm_retry_max_delay_seconds` | `LLM_MAX_RETRIES` / `LLM_RETRY_BASE_DELAY_SECONDS` / `LLM_RETRY_MAX_DELAY_SECONDS` | Retries of a transient model failure (2; at most 10, 0 turns them off) / backoff base and cap in seconds (1 / 20). See [the retry policy](llm-providers.md#retry-policy) |
| `agent_timeout_seconds` / `agent_recursion_limit` | `AGENT_TIMEOUT_SECONDS` / `AGENT_RECURSION_LIMIT` | Per chat or pipeline step agent limit (3600 seconds) / graph step limit (25) |
| `agent_tool_description_max_chars` | `AGENT_TOOL_DESCRIPTION_MAX_CHARS` | Maximum tool description length in the catalogue and planner prompt (300) |
| `mcp_timeout_seconds` / `mcp_servers` | `MCP_TIMEOUT_SECONDS` / `MCP_SERVERS` | MCP call limit (30 seconds; also bounds an integration's connection test and the address checks) / configured server JSON |
| `integrations_max_per_user` | `INTEGRATIONS_MAX_PER_USER` | How many MCP servers each user may connect on the Settings page (10) |
| `integrations_allow_private_network` | `INTEGRATIONS_ALLOW_PRIVATE_NETWORK` | `false`. With `APP_ENV=local` only, lets integrations reach loopback and private addresses (a dev server on `127.0.0.1`); production refuses to start with it on, `test` ignores it |
| `workspace_dir` | `AGENT_WORKSPACE_DIR` | Root of the per-user folders (`user-<id>`) that agents and the Files page share (`backend/workspace`; the image uses `/data/workspace`) |
| workspace/network policy | `AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS` | `false`: workspace readers and outbound web tools cannot be offered together; explicit opt-in required |
| workspace limits | `WORKSPACE_MAX_FILE_BYTES`, `WORKSPACE_MAX_OUTPUT_CHARS`, `WORKSPACE_SEARCH_MAX_FILES`, `WORKSPACE_SEARCH_MAX_RESULTS`, `WORKSPACE_CSV_MAX_ROWS` | Bound local reads, searches, output, and CSV rows; `WORKSPACE_MAX_FILE_BYTES` (2 MB) is also the largest artifact an agent saves |
| `workspace_max_total_bytes` | `WORKSPACE_MAX_TOTAL_BYTES` | Everything one user keeps, uploads and agent artifacts together (100 MB) |
| `workspace_upload_extensions` | `WORKSPACE_UPLOAD_EXTENSIONS` | Comma-separated types the Files page accepts, normalised to lower case with a dot (`.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.yaml,.yml,.html`) |
| `pdf_font_path` / `pdf_bold_font_path` | `PDF_FONT_PATH` / `PDF_BOLD_FONT_PATH` | TrueType faces embedded in PDF artifacts (DejaVu Sans under `/usr/share/fonts/truetype/dejavu/`); a missing file falls back to Helvetica (Western European text only) |
| `e2b_api_key` | `E2B_API_KEY` | Enables `run_python` (E2B code sandbox); empty or a placeholder leaves the tool out. Server-wide: every user who can run agents spends it |
| sandbox limits | `SANDBOX_TIMEOUT_SECONDS`, `SANDBOX_MAX_OUTPUT_CHARS`, `SANDBOX_MAX_FILES`, `SANDBOX_MAX_STREAM_CHARS` | Per `run_python` call: the whole call, from creating the sandbox to collecting its files, and the sandbox's lifetime (60 seconds), the report returned to the agent (10,000 characters), input files uploaded and output files or charts saved (10), and what the run may stream back before it is stopped (5,000,000 characters) |
| `pipeline_max_parallel_steps` | `PIPELINE_MAX_PARALLEL_STEPS` | Agent steps that can run at once in one stage (4) |
| `run_max_concurrent` / `run_shutdown_grace_seconds` | `RUN_MAX_CONCURRENT` / `RUN_SHUTDOWN_GRACE_SECONDS` | Background runs executing at once in the process; the rest wait queued (4) / how long active runs get on shutdown to record that they were interrupted (5 seconds) |
| `scheduler_enabled` / `scheduler_tick_seconds` / `schedules_max_per_user` | `SCHEDULER_ENABLED` / `SCHEDULER_TICK_SECONDS` / `SCHEDULES_MAX_PER_USER` | Whether this process starts scheduled runs (`true`; `false` keeps schedules saved but starts none) / how often it looks for due schedules, so a run starts at most this late (30 seconds, above 0) / how many schedules one account may have (20; `0` stops new ones) |
| document limits | `DOCUMENT_MAX_BYTES`, `DOCUMENT_MAX_CHARS`, `DOCUMENT_MAX_PAGES`, `DOCUMENT_MAX_UNPACKED_BYTES`, `DOCUMENT_MAX_SPREADSHEET_ROWS`, `DOCUMENT_MAX_IMAGE_PIXELS` | Bound one uploaded document: its size (10 MB), the text kept (120,000 characters), PDF pages, slides or TIFF pages read (300), what a `.docx`, `.xlsx` or `.pptx` may unpack to (50 MB), workbook rows read across all sheets (5,000; reading also stops past `DOCUMENT_MAX_CHARS` cells) and an image's pixels, checked before decoding (40 million). `DOCUMENT_MAX_BYTES` caps every upload, a run document or a file for the Files page, so `max_request_bytes` (`DOCUMENT_MAX_BYTES` plus 1 MB of multipart overhead) is the one request-size bound. The same limits apply when an agent reads a PDF or Word file from its workspace |
| document OCR | `DOCUMENT_OCR_ENABLED`, `DOCUMENT_OCR_LANGUAGES`, `DOCUMENT_OCR_MAX_PAGES`, `DOCUMENT_OCR_TIMEOUT_SECONDS`, `DOCUMENT_OCR_DPI` | Tesseract OCR for images and PDF pages without a text layer: on (`true`), languages `eng+fra` (Tesseract codes joined by `+`, validated), at most 30 pages per document, 15 seconds per page, PDF pages rendered at 300 dpi |
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

`create_app()` builds the app: it creates the `Database`, the OCR engine
(`app.state.ocr`, checked once because checking starts a `tesseract` process)
and the background run executor (`app.state.run_executor`, a
`BackgroundRunExecutor` whose thread starts with the first run), installs the
error handlers and middleware, and mounts `routes.api_router()` under `/api`.
Its `lifespan` marks runs a previous process left active as interrupted on
startup (`services/runs.interrupt_abandoned_runs`), starts the scheduler
(`app.state.scheduler`, built by `services/schedules/scheduler.build_scheduler`:
a `SchedulerLoop` thread, or an `IdleScheduler` when `SCHEDULER_ENABLED=false`),
and on exit stops the scheduler first (a tick in progress gets
`RUN_SHUTDOWN_GRACE_SECONDS` to finish) and then shuts the executor down.
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
| `Schedules` / `Now` | The signed-in user's schedules (`ScheduleAccess`: session, user, `SCHEDULES_MAX_PER_USER`, now) / the request's "now" in UTC (`Now` resolves `run_recorder.utcnow`; tests override that to fix the clock) |
| `ToolCatalog` | User-bound native and MCP tool discovery for the builder and planner |
| `TemplateUse` | The user, a session and their `StepDefaults` (model list, default first, and tool discovery that runs only once the template is found), for `POST /templates/{slug}/use` |
| `Agents` | A factory for the LangGraph chat agent, called after request validation |
| `Integrations` | An `IntegrationAccess` (session, user, `SecretBox`, `IntegrationRules`) for the Integrations endpoints; `host_resolver` supplies the DNS lookup its address checks use, so tests swap in a fake |
| `DocumentLimits` / `DocumentOcr` | The `ExtractionLimits` from settings / the OCR engine `create_app()` built once (`app.state.ocr`), or `None` when OCR is off or Tesseract or a language is missing |
| `UserFiles` | The signed-in user's `WorkspaceStorage` (their `user-<id>` folder, with `WORKSPACE_MAX_TOTAL_BYTES`) |
| `FileUploads` | The `UploadPolicy`: `DOCUMENT_MAX_BYTES` per file and `WORKSPACE_UPLOAD_EXTENSIONS` |

Tests replace any of these with `app.dependency_overrides`.

### `models.py` and `db.py`

| Model (table) | Fields | Invariants |
|---|---|---|
| `User` (`users`) | `username` (unique), `password_hash`, `created_at`, `llm_provider` (null = `LLM_PROVIDER`) | — |
| `ProviderSetting` (`provider_settings`) | `user_id` (FK, cascade), `provider`, `api_key_encrypted`, `api_key_hint`, `default_model` | **unique `(user_id, provider)`**; `""` means not saved |
| `Pipeline` (`pipelines`) | `name`, `user_id` (FK, cascade), `created_at`, `inputs` | `steps` load ordered by `(stage, order)` |
| `PipelineStep` (`pipeline_steps`) | `pipeline_id` (FK, cascade), `order`, `stage`, `title`, `role`, `allowed_tools`, `is_output`, `expected_output`, `prompt`, `model` | **unique `(pipeline_id, order)`** |
| `Integration` (`integrations`) | `user_id` (FK, cascade), `name`, `url`, `headers_encrypted` (one sealed JSON object), `header_hints` (JSON `{"name", "hint"}` list), `enabled`, `created_at` | **unique `(user_id, name)`**; `name` matches `INTEGRATION_NAME_PATTERN`; `""` means no headers |
| `Run` (`runs`) | `user_id` (FK, cascade), `pipeline_id` (FK, **set null** when the pipeline is deleted), `pipeline_name`, `definition` (JSON snapshot of the pipeline it runs), `input_text`, `input_values`, `trigger`, `schedule_id` (FK, **set null** when the schedule is deleted), `status`, `final_output`, `error_code`, `error_detail`, `created_at`, `started_at`, `finished_at` | `status` is a `RunStatus`, `trigger` a `RunTrigger` (`manual`, `schedule`, `chat`; `manual` for runs recorded before schedules); `""` error fields mean none; `steps` load ordered by `(stage, step_order)` |
| `Schedule` (`schedules`) | `user_id` (FK, cascade), `pipeline_id` (FK, **cascade**: deleting a pipeline deletes its schedules), `frequency`, `hour`, `minute`, `weekday`, `day_of_month`, `timezone`, `input_text`, `input_values`, `enabled`, `next_run_at` (UTC, indexed; null while off), `last_error`, `created_at` | `frequency` is a `ScheduleFrequency` (`hourly`, `daily`, `weekdays`, `weekly`, `monthly`); `hour`/`minute` are wall-clock in `timezone` (an IANA name); `weekday` (0 = Monday) only for weekly and `day_of_month` only for monthly, `null` otherwise; `""` `last_error` means the latest time started |
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
| `files.py` | `GET`/`POST /files`, `GET`/`DELETE /files/{path}` (download is a `FileResponse`, always an attachment) | `files.py`: `FileOut`, `FileListOut` |
| `integrations.py` | `GET`/`POST /integrations`, `PATCH`/`DELETE /integrations/{id}`, `POST /integrations/{id}/test` | `integrations.py`: `IntegrationIn`, `IntegrationPatch`, `HeaderIn`, `IntegrationOut`, `HeaderOut`, `IntegrationTestOut`, `IntegrationToolOut` |
| `pipelines.py` | list/create, get/put/patch/delete, `run` (waits for a recorded run; kept for compatibility), `generate`, `revise` | `pipelines.py`: `PipelineIn`, `PipelinePatch`, `PipelineOut`, `RunRequest`, `RunResponse`, `GenerateRequest`, `GenerateResponse`, `ReviseRequest` (`PipelineDraftIn`, `DraftStepIn`), `ReviseResponse`, `PipelineChangeOut` |
| `runs.py` | `POST /pipelines/{id}/runs` (202), `GET /runs` (paged), `GET /runs/{id}`, `POST /runs/{id}/cancel`, `POST /runs/{id}/resume`, `DELETE /runs/{id}` | `runs.py`: `RunListQuery`, `RunOut`, `RunSummaryOut`, `RunStepOut`, `RunDefinitionOut`, `RunPageOut` (+ `RunRequest` for the body) |
| `schedules.py` | `GET`/`POST /schedules`, `PATCH`/`DELETE /schedules/{id}`, `POST /schedules/{id}/run` (202, a run), `POST /schedules/preview` (declared before the id routes) | `schedules.py`: `ScheduleIn` (`ScheduleTimingIn` + `RunRequest` + `pipeline_id`), `SchedulePatch`, `ScheduleTimingIn`, `ScheduleListQuery`, `ScheduleOut`, `LastRunOut`, `SchedulePreviewOut` |
| `templates.py` | `GET /templates`, `POST /templates/{slug}/use` | `templates.py`: `TemplateOut`, `TemplateUseIn` (optional body); a used template answers with `PipelineOut` |

`schemas/common.py` holds the shared field types: `NonBlank` (trimmed, not
empty), `ModelId` (must be in some provider's catalogue), `ProviderName` and
`UtcDateTime` (a stored timestamp sent with its UTC offset). A step without `stage`
gets `stage = order`. A pipeline needs at least one step, and step orders must
be unique. Step `role` is optional (up to 100 characters); `allowed_tools` is
optional and, when explicit, contains unique, non-blank names. Tool availability
is checked when the agent runs. `PipelineInputField` validates each named
input through `services/pipeline_inputs.input_name_error`, the rule the planner
also applies; `RunRequest` only trims `input` and `inputs`, because which one a
run needs depends on the pipeline. `PipelineDraftIn`, the draft a revision
starts from, is checked like `PipelineIn` except that its name and step prompts
may be blank; the revise `instruction` is limited by
`REVISION_INSTRUCTION_MAX_LENGTH`.

### `repositories/`

| Module | Functions |
|---|---|
| `pipelines.py` | `for_user` (newest first, steps loaded), `get_owned` (or `NotFound`), `create_with_steps`, `replace_steps` (rename, redeclare the inputs and/or replace every step in one transaction), `delete`. Writes take a `PipelineChanges` value whose `None` fields are kept. |
| `runs.py` | `create` (run + its step rows), `get_owned` (or `NotFound`), `load`, `page_for_user` (newest first, summary columns only, total), and the compare-and-set writes `set_status`, `set_step`, `end` (final status + settling running steps), `reopen` (resume), plus `delete` and `interrupt_active` (startup recovery; a database without the runs table has none) |
| `schedules.py` | `for_user` (oldest first, optionally one pipeline's), `get_owned` (or `NotFound`), `get`, `count`, `create` / `save` (a `ScheduleFields` value), `delete`, `due(now)` (on, and `next_run_at <= now`, longest-waiting first), **`claim(id, seen, following)`** (the compare-and-set that moves `next_run_at` only while it still equals `seen`, so one caller starts each occurrence), `set_last_error`, `last_runs` (the newest run per schedule, summary columns only) |
| `users.py` | `get`, `get_by_username`, `create` |
| `provider_settings.py` | `for_user`, `get`, `save` (active provider + per-provider upsert in one transaction), `clear_key` (idempotent) |
| `integrations.py` | `for_user` (oldest first), `enabled_for`, `get_owned` (or `NotFound`), `name_taken`, `count`, `create`, `update` (an `IntegrationChanges` value whose `None` fields are kept), `delete` |
| `legacy_import.py` | `import_django_database` — the one-off copy from the old Django SQLite file |

Each write commits its own transaction.

### `services/`

| Module | Responsibility |
|---|---|
| `pipelines.py` | `prepare_run` (no steps → 400, snapshot through `multiagent/mapper.py`, bind the run's inputs — before anything is saved), `run` (in-process and unrecorded, for tests and one-off tools), and `generate` + `parse_plan` (tool-aware planner that also sanitises inputs and expected outputs). `ask_planner` is the one call-and-parse path that generation and revision share. |
| `runs.py` | `RunService`: `start` (save the run queued, hand it to the executor; a `RunStart` carries the `trigger` and `schedule_id`, and `launcher` marks chat runs `chat`), `run_to_end` / `run_saved_to_end` (start and wait: the compatibility endpoint and the chat tool), `resume`, `cancel`, `delete` (409 `Conflict` while active), and the job `_execute` (one attempt on the executor's loop, recording `succeeded`, `failed` or `interrupted`). `launcher()` binds it to one user for the chat agent; `interrupt_abandoned_runs()` runs at startup. Logs `run.cancelled`, `run.resumed`, `run.interrupted_on_startup` — never inputs or outputs. |
| `run_executor.py` | `RunExecutor` port (`submit(key, job) -> Future`, `cancel(key)`, `shutdown()`) and `BackgroundRunExecutor`: one asyncio loop on a daemon thread, started by the first job, at most `RUN_MAX_CONCURRENT` jobs at once. |
| `run_recorder.py` | `RunRecorder`, the `StepObserver` that writes each step event in its own short transaction (`STEP_CHANGES` registry: event kind → expected statuses + columns), and the run's `begin` / `end` with the endings `succeeded`, `failed`, `interrupted`, `cancelled`. Logs `run.started` and `run.finished` with status and duration. |
| `schedules/` | Scheduled runs (see [architecture.md](architecture.md#scheduled-runs)). `timing.py`: the pure rules, `Timing`, `FREQUENCIES` (one rule per preset: Strategy + Registry), `checked` (the one validation of a timing), `next_run_after(timing, after)` and `time_zone_error` — `zoneinfo` only, no clock, no database. `service.py`: the use cases behind the endpoints (`ScheduleAccess`, `ScheduleDraft`, `ScheduleEdit`/`TimingEdit`, `ScheduleView`; `create`, `update`, `delete`, `list_views`, `preview`, `run_now`), which check the pipeline's inputs with `prepare_run` before saving. `scheduler.py`: `Scheduler.tick()` / `fire()` (claim, then `RunService.start` with the owner's `ProfileAgents`, recording `last_error`), `SchedulerLoop` (the daemon thread) and `IdleScheduler` (when `SCHEDULER_ENABLED=false`), built by `build_scheduler`. Logs `schedule.created`, `schedule.updated`, `schedule.deleted`, `schedule.run_now`, `schedule.fired` (schedule, run and slot), `schedule.start_failed` (the error code), `schedule.fire_crashed` and `scheduler.started`/`stopped`/`tick_failed` — never inputs or outputs. |
| `pipeline_revision.py` | `revise`: applies one instruction to a draft through the planner (`prompts.pipeline_revision_prompt` → `ask_planner`), keeps the draft's name when the planner gives none, and returns a `Revision` (the whole sanitised pipeline and its changes). Saves nothing. |
| `pipeline_changes.py` | `diff_pipelines`: the pure change list a revision is reviewed with. Steps pair by content, title, prompt, then position (`STEP_MATCHERS`); a stage change is reported only when a step really runs at another point. |
| `documents/` | Turns an uploaded file into run-input text. `extraction.py` (`extract_document`: picks a reader by extension, enforces size, tidies and truncates, and appends each omission a reader reports, such as skipped pages; `extraction_limits(settings)`, the limits for the endpoint and for agents reading workspace files alike; `megabytes()` for limit messages), `readers.py` (the `READERS` registry; plain text, and HTML via `toolbox/html_text.py`; every third-party parser is registered through `guarded`, which re-raises anything it throws as `DocumentUnreadable`), `pdf.py` (pypdf text layer; pages without one are rendered with PDFium through pypdfium2, under one process-wide lock because PDFium is not thread-safe), `images.py` (Pillow with only the PNG, JPEG, WebP, TIFF, BMP and GIF decoders, a pixel cap checked from each frame's header, TIFF pages counted by seeking, transparency onto white, 16-bit gray scaled, EXIF rotation), `office.py` (Word via python-docx, Excel via openpyxl in read-only mode, reading a sheet's real size rather than its declared one, PowerPoint via python-pptx with a `singledispatch` registry per shape kind; all three behind the unpacked-size zip guard), `scans.py` (`PageOcr`: the per-document OCR page cap, a page OCR times out or fails on skipped rather than the document, and the `[Not read: ...]` sentences), `ocr.py` (`TesseractOcr`, the adapter over pytesseract, and `ocr_engine`, which `create_app()` calls once and which returns `None`, logging why, when OCR is off or the binary or a language is missing), and `contracts.py` (`ExtractionLimits`, `ReadContext`, `ReadResult`, `ExtractedDocument`, and the `OcrEngine` port). Stateless: nothing is stored. A new format is one reader and one registry entry. |
| `pipeline_inputs.py` | Named run inputs: `input_name_error` (the naming rule) and `bind_run_inputs`, which checks a run's text or values against the declared inputs and builds the first stage's input — before any agent starts. |
| `templates/` | Mission templates (Registry): `contracts.py` (frozen `MissionTemplate` and `TemplateStep`, inputs as the shared `InputField`; templates never name a model), `review.py` (`Review`, the builder of the reviewer step every template ends with), one module per theme (`research.py`, `documents.py`, `data.py`, `marketing.py`, `launch.py`), `registry.py` (`CATALOGUE` in gallery order, `get_template` or `NotFound`) and `use.py` (`use_template`: builds the steps through `pipelines.sanitise_step`, the planner's sanitiser, so each step gets the owner's default model and only the tools they have, then saves through the repository). A new template is one entry in a theme module. |
| `multiagent/contracts.py` | Immutable `PipelineSpec` / `StepSpec` / `InputField` snapshots, `RunInputs`, run-result data, the async `StepAgent` protocol, and the observer port: `StepEventKind` (started, succeeded, failed, cancelled), `StepEvent`, `StepObserver`, `SILENT_OBSERVER` and `RunControl` (observer + results already completed). |
| `multiagent/mapper.py` | Copies loaded ORM pipeline and step fields into graph contracts before concurrent execution; `spec_to_json` / `spec_from_json` store a run's snapshot. |
| `multiagent/graph.py` | LangGraph `StateGraph`: one agent node per saved step, concurrent nodes within a stage, a barrier/join before the next stage, and result ordering by saved step order. Each node reports its step to the run's observer, and returns a completed step's saved result without running its agent (resume). `output_orders` decides which steps are outputs. The concurrency cap comes from `PIPELINE_MAX_PARALLEL_STEPS`; this module logs `pipeline.run`. |
| `multiagent/step_agent.py` | User-bound LangGraph step agent: selected model, role, native/MCP tools, final text, and tool call metadata. |
| `prompts.py` | `step_prompt` (fills `{input}` and `{name}` in one pass), `merge_stage_outputs`, `merge_input_values`, `pipeline_generation_prompt` and `pipeline_revision_prompt` (both built on `PIPELINE_PLANNER_GUIDE`; the revision fences the draft and the instruction as data), `step_agent_system_prompt` (role, expected output, tool guidance). |
| `chat.py` | `stream_reply` — eager first chunk, then an async generator that logs mid-stream failures. |
| `agent.py` | Builds and streams the chat-only LangGraph agent. |
| `agent_runtime.py` | Shared chat/pipeline tool policy, limits, and third-party failure translation. |
| `agent_types.py` | Immutable step task, agent outcome, tool descriptor, and tool call trace. |
| `agent_tools.py` | Authenticated `list_pipelines`, `inspect_pipeline`, and `run_pipeline` functions. Each call opens its own session and uses the ownership-scoped repository; `run_pipeline` goes through the run service (`PipelineLauncher`), so chat runs are recorded. `native_tools` adds the built-in toolbox. |
| `toolbox/` | Built-in agent tools: `registry.py` (name → builder, filtered by `AGENT_BUILTIN_TOOLS`), `tools.py` (LangChain adapters), `web.py` (Tavily search and SSRF-guarded fetch), `workspace.py` (`LocalWorkspace`: bounded text, search, CSV rows, PDF/Word read through the document readers, and artifacts; every `DomainError` from the storage becomes a `ToolException` the model sees), `calculator.py`, `html_text.py`, and `config.py`. See [architecture.md](architecture.md#built-in-tools). |
| `toolbox/` code sandbox | `run_python`: `sandbox.py` (the `CodeSandbox` port, value objects and one call's lifecycle: timeout, always-closed sandbox, `sandbox.run` log), `e2b_sandbox.py` (the E2B adapter: offline, short-lived sandboxes; SDK errors become `SandboxError`; stream budget), `code_runner.py` (workspace files in and out, the report). |
| `files/` | The user's files, shared by the agents and the Files page. `storage.py`: `user_workspace_dir(root, user_id)` (the one "folder of user X" helper) and `WorkspaceStorage` — the single confinement core (relative, visible paths only, nothing outside the root, no links followed, no overwrite unless asked, the `WORKSPACE_MAX_TOTAL_BYTES` quota checked before a write and again after a new file is written, `prepare()` for a `0700` folder). `service.py`: `list_files`, `download`, `upload` (`UploadPolicy`, `Upload`) and `delete` for the endpoints, returning `FileListing` / `FileEntry` / `FileDownload`. `names.py`: `safe_filename`, `media_type` (a fixed map per extension), `file_type`. |
| `artifacts/` | Agent deliverables as real files. `registry.py`: `RENDERERS` (extension → renderer, Strategy + Registry) and `render_artifact(extension, content, options)`, which re-raises any failure inside python-docx or ReportLab as `ValidationFailed`. `markdown.py`: `parse_markdown` (markdown-it-py, HTML kept as text) into one block model both writers walk. `docx_writer.py` (Word styles, real numbered lists and hyperlinks) and `pdf_writer.py` (ReportLab Platypus, TrueType from `PDF_FONT_PATH`, Helvetica fallback), each with one `singledispatch` writer per block type. `contracts.py`: `RenderOptions`, `Renderer`. |
| `addresses.py` | The SSRF guard shared by `fetch_url` and integrations: `resolve_host`, `is_public` and `ensure_public_host`, which raises `AddressNotAllowed` unless every address a host resolves to is global. |
| `mcp.py` | Converts validated HTTP or stdio MCP server settings into bounded adapter connections (optionally with an HTTP client factory), and defines `MCPConnections(operator, user)`. |
| `mcp_discovery.py` | `discover_tools`: operator servers must answer (else `tool_unavailable`); each integration loads through `load_server_tools` and is skipped with a warning when it fails. `REASONS` turns MCP failures into plain words. See [architecture.md](architecture.md#mcp-servers-and-tool-discovery). |
| `integrations/` | Settings → Integrations. `service.py` (list, create, update, delete, `test_connection`), `rules.py` (`IntegrationRules`, `AddressPolicy`: https only, http and private addresses for local development only, `ensure_reachable`), `headers.py` (seal, reveal, hint and merge header values), `connections.py` (`mcp_connections_for`, the one builder of a user's MCP connections, and `GuardedClientFactory`, which re-checks the address before every request). |
| `tool_catalog.py` | Discovers native read tools, configured MCP tools and the user's integration tools for `GET /agent-tools` and the planner; `describe` cuts a description to `AGENT_TOOL_DESCRIPTION_MAX_CHARS`. |
| `pipeline_agents.py` | Compatibility re-export of `multiagent.step_agent.PipelineAgentGenerator`. |
| `accounts.py` | `register` (password policy, unique username), `sign_in` → `TokenPair`, `refresh_access`, `authenticate`. |
| `password_policy.py` | The four rules Django applied: similarity to the username, minimum length 8, Django's common-password list (`api/data/common-passwords.txt.gz`), entirely numeric. |
| `llm.py` | **The only reader of provider credentials and transport settings** (timeout, base URL, retry policy). `LLMProfile`, `provider_config(profile)`, `get_provider(profile)` and `get_agent_model(profile, model_id)`. A saved key wins over the `.env` one. |
| `llm_settings.py` | The Settings page: `resolve_profile()` (per request), `read()`, `save()`, `remove_key()`, and `environment_profile()` for the CLI. Keys are sealed with `SecretBox` and only their hint is returned. |
| `catalog.py` | `available_model_ids()` (default first), `default_model_id()` and `known_model_ids()`, for a given provider or `LLM_PROVIDER`. |
| `errors.py` | `PROVIDER_ERROR_MAP` and `as_domain_error()` — the one translation from `llm` errors to domain errors. |

### `security.py`

Pure functions with no web framework. `hash_password` / `verify_password` use
Django's `pbkdf2_sha256$<iterations>$<salt>$<hash>` format, so accounts imported
from the old backend keep their passwords. `TokenSigner` issues and reads HS256
JWTs with `token_type` (`access` or `refresh`) and `user_id` claims.
`SecretBox` encrypts saved API keys and integration header values with Fernet,
keyed by HKDF over `SECRET_KEY`; a secret sealed under another `SECRET_KEY`
raises `UnreadableSecret`.

### `exceptions.py`, `errors.py` and `middleware.py`

`DomainError(detail)` carries a class-level `code`, `status_code` and optional
`headers`. The subclasses are `ValidationFailed` (400), `NotAuthenticated` (401,
`WWW-Authenticate: Bearer`), `NotFound` (404), `Conflict` (409, e.g. deleting a
run in progress), `ProviderNotConfigured` (503),
`ProviderUnavailable` (502), `ToolUnavailable` (502), `ProviderTimedOut` (504),
`UpstreamResponseInvalid` (502), for documents `DocumentTooLarge` (413),
`UnsupportedDocument` (415) and `DocumentUnreadable` (422), whose subclass
`OcrTimedOut` lets a multi-page reader skip the one page OCR gave up on, and
for files `FileAlreadyExists` (409 `file_exists`), `FileTooLarge` (413),
`StorageQuotaExceeded` (413 `storage_quota_exceeded`) and `UnsupportedFileType` (415).

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
| `schedules/support.py`, `schedules/conftest.py` | The schedules tests' kit (their own package, `tests/schedules/`): `Clock`, a clock the test sets (the `clock` fixture installs it as `utcnow`, so every request's "now" is its); fake owner agents `StaticAgents`, `FlakyAgents` (fails like an account without a key) and `BrokenAgents` (hits a bug); `scheduler(app, agents, clock)`, a `Scheduler` over the inline executor; builders (`new_schedule`, `create_schedule`, `body`, `listing`), time helpers (`utc`, `when`, `chain`, `local`) and the `api`, `pipeline` and `stranger` fixtures |
| `default_model` | The active default model id |
| `retry_fakes.py` | Provider failures as each SDK raises them, a `FakeClock` that records retry waits instead of sleeping, and ready `ProviderConfig`s |
| `mcp_fakes.py`: `resolver(table)`, `FakeServers(behaviour)` | Offline DNS (override `host_resolver`) and MCP servers (patch `mcp_discovery.MultiServerMCPClient`) for the integration tests |

| Test module | Covers |
|---|---|
| `test_endpoints.py` | HTTP behaviour: every non-public route needs auth, auth flows, CRUD, run, generate, chat |
| `test_errors.py` | The error shape for 400/401/404/405/500 |
| `test_schemas.py` | Model-id validation, stages, required steps, non-blank fields |
| `test_security.py` | Django-compatible hashes (checked against a hash Django produced), password policy, tokens |
| `test_database.py` | Migrations match the models and keep existing pipelines and steps; the Django import |
| `test_pipeline_service.py` | `run`, parallel stages, outputs, `parse_plan`, prompts |
| `test_pipeline_inputs.py` | Named run inputs and expected outputs: binding, placeholder filling, planner sanitising, and the HTTP contract |
| `test_templates.py` | Every template passes the saved-pipeline validation and its field limits, uses exactly its declared placeholders, fans out then ends with a lone reviewer, and grants only known built-in tools; the gallery and use endpoints (default model, tool filtering, naming, ownership, unknown slug, a run on the named inputs) |
| `test_pipeline_revision.py` | The revision prompt (shared guide, fenced user data), `revise`, and `POST /pipelines/revise`: happy path, nothing saved, unfinished drafts, validation, 502/503 |
| `test_pipeline_changes.py` | `diff_pipelines`: step pairing, changed fields, stage moves versus renumbering, inputs, renames, malformed planner data |
| `test_multiagent_graph.py` | LangGraph stage barriers, bounded concurrency, result ordering, failure propagation, step events, reuse of completed steps, snapshot round trip |
| `test_runs_service.py` | Background runs end to end: recording, failure (and the cancelled parallel sibling), crashes, stop while running or queued, the concurrency limit, resume after failure (with the run's own snapshot), restart recovery, shutdown, delete |
| `test_runs_api.py` | The runs HTTP surface: 202 start and polling, validation before saving, resume, idempotent stop, 409 delete, paging and filtering, ownership, the recorded compatibility endpoint, a run outliving its pipeline |
| `schedules/test_timing.py` | Next-run computation: every preset, the zone's calendar rather than UTC's, the hour the clocks skip and the one they repeat (Paris, New York), hourly across both changes, weekends, the 31st in short months and leap years, a half-hour zone, and steady gaps over two windows holding this year's clock changes in five zones |
| `schedules/test_timing_checks.py` | `checked` and `time_zone_error`: known and unknown zones (path-like names included), the day a weekly or monthly schedule needs, the fields a frequency does not use, seconds dropped |
| `schedules/test_scheduler.py` | `Scheduler` with a test clock and inline runs: a due schedule starts a run marked as its own, the owner's agent and inputs, not before its time, off means never, overdue after downtime runs once, **two threads racing for one occurrence start exactly one run** (a file database), `claim` as a compare-and-set, a stale snapshot starts nothing after an edit, and inputs read when the run starts |
| `schedules/test_scheduler_failures.py` | A time that cannot start is recorded on the schedule and the schedule moves on: no key (a fake and the real `ProfileAgents`), inputs that no longer fit, no steps, a bug in one schedule not stopping the others |
| `schedules/test_scheduler_loop.py` | `SchedulerLoop` (ticks, survives a failing tick, restarts, `stop` is idempotent), `build_scheduler` from settings, and the lifespan starting the scheduler and stopping it before the executor |
| `schedules/test_api_create.py` | `POST` and `GET /schedules`: create with its next run, fields a frequency does not use, every refusal (zone, time, missing day, input rules, no steps, the per-account limit), a pipeline that is not yours, listing, filtering and ownership |
| `schedules/test_api_change.py` | `PATCH /schedules/{id}`: the next run worked out again, idempotence, off and on, inputs checked again (off always works), a due time kept, invalid changes, and the reason a time failed cleared by an edit that changes what runs or when |
| `schedules/test_api_actions.py` | Delete (the runs stay, unlinked), cascade from the pipeline, ownership on every route, run now (also while off, failing, or with inputs that no longer fit), preview, and the trigger and last error shown |
| `schedules/test_migration.py` | The schedules migration on a database that already holds a run: run steps survive upgrade and downgrade (a rebuild of `runs` must not cascade-delete them), old runs read `manual`, the foreign keys still act |
| `test_run_triggers.py` | What started a run: chat, the API (both endpoints) and a resume |
| `test_llm_providers.py` / `test_llm_catalog.py` | Provider adapter, registry, catalogue |
| `test_llm_retry.py` | The retry policy: retried and failing statuses, connection errors, timeouts, backoff, `Retry-After`, logging, streams |
| `test_llm_provider_retries.py` / `test_agent_model_retries.py` | Retries on the direct provider and on the LangChain models (SDK retries off, exact attempt counts, no replayed stream), and the settings behind them |
| `test_chat_agent.py` | MCP settings, discovery, streaming and failure mapping |
| `test_pipeline_agents.py` | Step model selection, MCP tool calls, and discovery failures |
| `test_agent_tools.py` | Native pipeline functions, ownership, and chat tool invocation |
| `test_toolbox.py` / `test_web_tools.py` | Built-in tools: calculator safety, HTML text, registry, search, SSRF guard, size caps, workspace reads (PDF and Word too), artifacts in every format with their limits and the quota, and a run that survives a failing tool |
| `test_file_storage.py` | `WorkspaceStorage`: traversal, hidden, absolute, NUL and over-long paths, links, overwrite refusal and replace, the quota (also when a write ends over it), deletes; safe upload names and media types |
| `test_files.py` | The Files API: listing, upload (safe names, several files, overwrite refusal, extension and size refusals, quota), download headers (attachment, nosniff, sandbox CSP, non-ASCII names), path tricks, links, ownership, and one folder shared with the agents |
| `test_artifacts.py` | The Markdown model, the Word writer (styles, numbering restarts, links), the PDF writer (non-Latin text with DejaVu, the Helvetica fallback, links, pages), and the registry |
| `test_integrations.py` | Integrations over HTTP: CRUD, ownership, header values encrypted at rest and never returned, keeping and replacing headers, validation, the per-user limit, and SSRF refusal (private, loopback, link-local, metadata and shared addresses; http outside local) |
| `test_integration_tools.py` | `mcp_connections_for` (operator servers + enabled integrations, skipped ones), the per-request address guard, discovery that skips a failing integration, tool-name clashes, and the catalogue's source labels |
| `test_integration_runs.py` | Runs that do or do not need a failing integration, a step getting the integration tools it selected, and `POST /integrations/{id}/test` (tools found, every failure reason, a re-checked address, unreadable headers) |
| `test_sandbox_tool.py` / `test_sandbox_lifecycle.py` / `test_sandbox_wiring.py` / `test_e2b_sandbox.py` | `run_python` over an in-memory sandbox (`sandbox_fakes.py`): the report, truncation, input confinement, output limits and no overwrites; fresh, always-closed sandboxes, one deadline, the boundary log; the key and data-leak rules; the E2B adapter against a fake SDK (`e2b_fakes.py`: offline creation, error mapping, stream and download budgets) |
| `test_settings_and_config.py` | Settings parsing, legacy names, production guards, request URLs kept out of the logs |
| `test_documents.py` | Document extraction: text, HTML, PDF and Word, limits, refusals, the HTTP contract and the request-size guard |
| `test_document_scans.py` | Scanned and mixed PDFs through a fake `OcrEngine`: render resolution and pixel cap, OCR page cap, a page that times out or fails, OCR off |
| `test_document_images.py` | Every image type, TIFF pages (counted without `n_frames`), transparency, 16-bit scans, EXIF rotation, the pixel cap and decompression bombs, decoders allowed, OCR off |
| `test_document_office.py` | `.xlsx` and `.pptx` text, row and slide limits, the shared zip-bomb guard |
| `test_document_ocr.py` | The Tesseract adapter and the startup check (pytesseract and the binary faked), OCR settings; one test runs the real binary and is skipped where it is not installed (CI) |

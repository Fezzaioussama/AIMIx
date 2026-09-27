# Backend reference

Django 5 + Django REST Framework + SimpleJWT, run with `uv`. The import root is
`backend/`: the top-level packages are `config`, `api`, and `llm`.

```
backend/
  manage.py                 # defaults to config.settings.local
  config/                   # wiring only
  api/                      # the HTTP application
  llm/                      # provider layer, framework-agnostic
  tests/                    # pytest suite
```

## `config/` — project wiring

| File | Role |
|---|---|
| `settings/base.py` | Shared settings. Loads `backend/.env` with `python-dotenv`. Helpers `env_str`, `env_bool`, `env_list`, `env_float`, `env_secret` (treats placeholders as empty). Defines DRF defaults (JWT auth, **`IsAuthenticated` by default**, custom exception handler), SimpleJWT lifetimes, the `LLM_*` settings, and logging for the `api` and `llm` loggers. |
| `settings/local.py` | Dev: `DEBUG` on, fallback insecure key. |
| `settings/test.py` | In-memory DB, MD5 hasher, **empty provider keys** so tests can never reach a real LLM. |
| `settings/production.py` | Refuses unsafe config (`ImproperlyConfigured`), enables HSTS, SSL redirect, secure cookies. |
| `urls.py` | `admin/` and `api/` → `api.urls`. |
| `wsgi.py` / `asgi.py` | Default to production settings. |

LLM-related settings (all from env, see `.env.example`):

| Setting | Source | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `LLM_PROVIDER` | `openrouter` (default) or `togetherai`; aliases accepted |
| `LLM_TIMEOUT_SECONDS` | `LLM_TIMEOUT_SECONDS` | Timeout passed to the SDK client, per call (default 3600 = one hour) |
| `LLM_API_KEYS[provider]` | `OPEN_ROUTER_KEY` (or `OPENROUTER_API_KEY`), `TOGAI_API_KEY` | Credentials |
| `LLM_BASE_URLS[provider]` | `OPENROUTER_BASE_URL`, `TOGETHERAI_BASE_URL` | Optional override (proxy/gateway) |
| `LLM_DEFAULT_MODELS[provider]` | `OPENROUTER_DEFAULT_MODEL`, `TOGETHERAI_DEFAULT_MODEL` | Default model id |
| `PIPELINE_MAX_PARALLEL_STEPS` | `PIPELINE_MAX_PARALLEL_STEPS` | Provider calls one parallel stage makes at once (default 4) |

## `api/` — the HTTP application

### `models.py`

| Model | Fields | Invariants |
|---|---|---|
| `Pipeline` | `name`, `user` (FK, cascade), `created_at` | Ordered newest first |
| `PipelineStep` | `pipeline` (FK, `related_name="steps"`), `order`, `prompt`, `model` | Ordered by `order`; **unique `(pipeline, order)`** |

`PipelineStep.model` is a free `CharField` in the database; validity is enforced
by the serializer against the catalogue, not by the DB.

### `urls.py`

Routing table only. A DRF `DefaultRouter` registers `PipelineViewSet` at
`pipelines/`; function views cover auth, chat, models, run, and generate. See
[api-reference.md](api-reference.md).

### `endpoints/`

| Module | Views | Notes |
|---|---|---|
| `auth.py` | `RegisterView` (public, `AllowAny`), `protected_view` | Login/refresh are SimpleJWT's own views, wired in `urls.py` |
| `chat.py` | `chat_view` | Returns `StreamingHttpResponse` from `services/chat.stream_reply` |
| `models.py` | `list_models` | `{"models": [...], "default": "..."}` |
| `pipelines.py` | `PipelineViewSet`, `run_pipeline`, `generate_pipeline` | Queryset always via `repository.for_user` |

### `serializers/`

Re-exported from `api/serializers/__init__.py`, so import from `api.serializers`.

| Serializer | Contract |
|---|---|
| `RegisterSerializer` | `username`, `password` (write-only, Django password validators) |
| `ChatRequestSerializer` | `prompt` (non-blank) |
| `PipelineStepSerializer` | `id`, `order`, `prompt`, `model` — `model` checked by `_validate_model_id` |
| `PipelineSerializer` | `id`, `name`, `user` (read-only), `created_at` (read-only), nested `steps` (at least one). `create`/`update` delegate to the repository |
| `RunPipelineSerializer` | `input` (non-blank) |
| `GeneratePipelineSerializer` | `description` (non-blank), `planner_model` (optional, validated, defaults to the default model) |

### `repositories/pipelines.py`

| Function | Purpose |
|---|---|
| `for_user(user)` | Owned pipelines with `steps` prefetched |
| `get_owned(user, id)` | One owned pipeline or `NotFound` |
| `create_with_steps(...)` | Atomic create of pipeline + steps (`bulk_create`) |
| `replace_steps(pipeline, name, steps)` | Atomic rename and/or delete-and-recreate of all steps |

### `services/`

| Module | Responsibility |
|---|---|
| `pipelines.py` | `run` (the step loop, returns `RunResult`), `generate` + `parse_plan` (planner), `ensure_runnable`. DTOs `StepResult`, `RunResult`. Logs `pipeline.run` with id, step count, duration. |
| `prompts.py` | `step_prompt` (replace `{input}`, else append `"\n\nInput: ..."`), `pipeline_generation_prompt`. |
| `chat.py` | `stream_reply` — eager first chunk, then a generator that logs mid-stream failures. |
| `llm.py` | **The only reader of provider settings.** `provider_config()` builds a `ProviderConfig`; `get_provider()` builds the provider via the registry. |
| `catalog.py` | `available_model_ids()` (default first) and `default_model_id()` for the active provider. |
| `errors.py` | `PROVIDER_ERROR_MAP` and `as_domain_error()` — the one translation from `llm` errors to domain errors. |

### `exceptions.py` and `errors.py`

`DomainError(detail)` carries a class-level `code` and `status_code`.
Subclasses: `ValidationFailed` (400), `NotFound` (404),
`ProviderNotConfigured` (503), `ProviderUnavailable` (502),
`ProviderTimedOut` (504), `UpstreamResponseInvalid` (502).

`errors.exception_handler` is registered in `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.
It renders `DomainError` directly, maps DRF errors by status via `STATUS_CODES`,
and flattens nested DRF validation detail into one sentence (`_flatten`).

### `http.py`

`authenticated_user(request)` narrows `request.user` from
`User | AnonymousUser` to `User` for type safety.

### `management/commands/llm_probe.py`

```bash
cd backend
uv run python manage.py llm_probe --list-models     # what `make run-llm` does
uv run python manage.py llm_probe "Say hi"          # one real call, default model
uv run python manage.py llm_probe "Say hi" --model openai/gpt-oss-120b
```

## `llm/` — provider layer

Covered in [llm-providers.md](llm-providers.md).

## `tests/`

pytest + pytest-django, settings `config.settings.test`. `conftest.py` provides:

| Fixture / helper | Use |
|---|---|
| `FakeProvider` | Implements `LLMProvider` with canned `reply` / `chunks`; records `calls` |
| `FailingProvider(error)` | Raises the given `LLMError` from `generate` and `stream` |
| `fake_provider` | Monkeypatches `get_provider` in the pipelines and chat endpoints |
| `user`, `password`, `client`, `auth_client` | A user and an authenticated `APIClient` |
| `default_model` | The active default model id |

| Test module | Covers |
|---|---|
| `test_endpoints.py` | HTTP behaviour: auth, CRUD, run, generate, chat, error shapes |
| `test_pipeline_service.py` | `run`, `parse_plan`, prompt substitution |
| `test_serializers.py` | Model-id validation, required steps |
| `test_errors.py` | Error handler and flattening |
| `test_llm_providers.py` | Adapter behaviour, error normalisation, registry |
| `test_llm_catalog.py` | Catalogue lookups |
| `test_settings_and_config.py` | Env helpers and production guards |

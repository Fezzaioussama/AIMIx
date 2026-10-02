# LLM provider layer

`backend/llm/` is a small, **framework-agnostic** package: it never imports
FastAPI, SQLAlchemy, `api`, or `config`. Everything it needs arrives as a
`ProviderConfig`. That keeps it unit-testable with a fake client and reusable
outside this app.

```
llm/
  base.py          # ProviderConfig, LLMProvider Protocol, OpenAICompatibleProvider
  agent_models.py  # LangChain model factory registry for LangGraph chat
  exceptions.py    # LLMError, ProviderNotConfigured, ProviderTimeout, ProviderRequestError
  registry.py      # FACTORIES, ALIASES, canonical_name, create_provider
  catalog.py       # ModelInfo, ModelCatalog, OpenRouterModels, TogetherAIModels, CATALOGS
  providers/
    openrouter.py  # builds an openai.OpenAI client with the OpenRouter base URL
    together.py    # builds a together.Together client
```

## The contract

```python
class LLMProvider(Protocol):
    name: str

    def generate(self, prompt: str, model: str | None = None) -> str: ...
    def stream(self, prompt: str, model: str | None = None) -> Iterator[str]: ...
```

Every implementation must:

- raise **only** `ProviderTimeout` or `ProviderRequestError` on a failed call
  (and `ProviderNotConfigured` when it cannot be built);
- never return `""` to mean failure — an empty string means the model really
  produced nothing;
- never log the prompt (it can contain user data).

## `OpenAICompatibleProvider`

Both OpenRouter and TogetherAI expose an OpenAI-shaped
`client.chat.completions.create(model=..., messages=[...], stream=...)`, so one
class implements the transport for both:

- `_resolve_model` — explicit model, else `config.default_model`, else error.
- `_create` — the one place that catches a broad `Exception` from the SDK. It
  logs `llm.request_failed` (provider, model, error class — no prompt) and
  re-raises as `ProviderTimeout` if the class name contains "timeout", otherwise
  `ProviderRequestError`, always `from cause`.
- `generate` — returns `choices[0].message.content`.
- `stream` — yields non-empty `choices[0].delta.content` pieces.

The call sends a single user message; there is no system prompt, history,
temperature, or max-tokens setting today.

**Retries:** none. Both SDK clients are built with `max_retries=0` (the SDKs
retry twice by default, which would multiply a long timeout), so a failure
surfaces to the user immediately. Add bounded retries with backoff only for idempotent calls
(AGENTS.md §6).

## How a provider gets built

```
settings.LLM_PROVIDER ──► registry.canonical_name()  ("open_router" → "openrouter")
                      ──► api/services/llm.provider_config()  → ProviderConfig
                      ──► registry.create_provider(name, config)
                      ──► FACTORIES[name](config)  → providers/<name>.build()
                      ──► OpenAICompatibleProvider(name, client, config)
```

`get_provider()` builds an SDK client for pipeline planning. Chat and pipeline
steps use `get_agent_model()` and the `agent_models.py` registry to construct a
LangChain model for the configured provider; steps pass their selected model id.
LangGraph then orchestrates MCP tool calls. Both model adapters set explicit
request timeouts and disable SDK retries.

## The model catalogue

`llm/catalog.py` is the **single source of truth for valid model ids**. Each
provider has a `ModelCatalog` subclass whose class attributes are `ModelInfo`
value objects (`model_id`, capability flags, description). `CATALOGS` maps a
provider name to its catalogue.

It is used in three places, which is why they can never disagree:

1. `PipelineStepSerializer` and `GeneratePipelineSerializer` reject unknown ids.
2. `GET /api/models` serves the list to the frontend (`useModels`).
3. The planner prompt lists the allowed ids, and `parse_plan` replaces any
   other id with the default.

The default model comes from `LLM_DEFAULT_MODELS[provider]` (env), falling back
to the first catalogue entry. `available_model_ids()` puts the default first.

## Recipe: add a model

1. Add a `ModelInfo(...)` attribute to the right class in `llm/catalog.py`,
   using the exact id the provider expects.
2. Check it: `cd backend && uv run python -m api.cli llm-probe "hi" --model <id>`.
3. `make check`. The frontend picks it up automatically from `/api/models`.

## Recipe: add a provider

Example: a hypothetical `groq` provider with an OpenAI-compatible API.

1. `llm/providers/groq.py`:
   ```python
   from __future__ import annotations

   from openai import OpenAI

   from llm.base import LLMProvider, OpenAICompatibleProvider, ProviderConfig
   from llm.exceptions import ProviderNotConfigured

   NAME = "groq"
   DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


   def build(config: ProviderConfig) -> LLMProvider:
       if not config.api_key:
           raise ProviderNotConfigured("GROQ_API_KEY is not set.")
       client = OpenAI(
           base_url=config.base_url or DEFAULT_BASE_URL,
           api_key=config.api_key,
           timeout=config.timeout_seconds,
       )
       return OpenAICompatibleProvider(NAME, client, config)
   ```
2. `llm/registry.py`: add `groq.NAME: groq.build` to `FACTORIES` and any
   spellings to `ALIASES`.
3. `llm/catalog.py`: add a `GroqModels(ModelCatalog)` class and a `CATALOGS`
   entry.
4. `config/settings.py`: add `groq_api_key`, `groq_base_url` and
   `groq_default_model` fields, and a `"groq"` entry in the `llm_api_keys`,
   `llm_base_urls` and `llm_default_models` properties; set the empty key in
   `TEST_SETTINGS` (`tests/conftest.py`).
5. `backend/.env.example`: document `GROQ_API_KEY`, `GROQ_BASE_URL`,
   `GROQ_DEFAULT_MODEL`, and add `groq` to the supported values comment.
6. Tests in `tests/test_llm_providers.py`: build fails without a key; errors
   normalise to `ProviderTimeout` / `ProviderRequestError`.
7. Add a LangChain chat model builder in `llm/agent_models.py` so chat can use the provider.
8. `make check`.

If the new SDK is **not** OpenAI-shaped, write a separate adapter class that
implements `LLMProvider` and honours the same error contract, rather than
branching inside `OpenAICompatibleProvider`.

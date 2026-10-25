# LLM provider layer

`backend/llm/` is a small, **framework-agnostic** package: it never imports
FastAPI, SQLAlchemy, `api`, or `config`. Everything it needs arrives as a
`ProviderConfig`. That keeps it unit-testable with a fake client and reusable
outside this app.

```
llm/
  base.py          # ProviderConfig, LLMProvider Protocol, OpenAICompatibleProvider
  agent_models.py  # LangChain model factory registry for LangGraph chat, with retries
  retry.py         # RetryPolicy, Retrier: bounded retries for transient failures
  usage.py         # TokenUsage, cost sources, UsageCallback, metered: what each model call used and cost
  exceptions.py    # LLMError, ProviderNotConfigured, ProviderTimeout, ProviderRequestError
  registry.py      # FACTORIES, ALIASES, canonical_name, create_provider
  catalog.py       # ModelInfo, ModelCatalog, OpenRouterModels, TogetherAIModels, CATALOGS
  providers/
    openrouter.py  # builds an openai.OpenAI client with the OpenRouter base URL
    together.py    # builds an openai.OpenAI client with the Together base URL
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
- retry only through the policy in `llm/retry.py`, with the SDK's own retries
  switched off (see [Retry policy](#retry-policy));
- never log the prompt (it can contain user data).

## `OpenAICompatibleProvider`

Both OpenRouter and TogetherAI expose an OpenAI-shaped
`client.chat.completions.create(model=..., messages=[...], stream=...)`, so one
class implements the transport for both:

- `_resolve_model` — explicit model, else `config.default_model`, else error.
- `_create` — the SDK call; `generate` and `stream` run it under the retry
  policy (below).
- `_normalised_failures` — the one place that catches a broad `Exception` from
  the SDK, once the retries are spent. It logs `llm.request_failed` (provider,
  model, error class — no prompt) and re-raises as `ProviderTimeout` if the
  class name contains "timeout", otherwise `ProviderRequestError`, always
  `from cause`. A failure in the middle of a stream is normalised the same way.
- `generate` — returns `choices[0].message.content`.
- `stream` — yields non-empty `choices[0].delta.content` pieces.

The call sends a single user message; there is no system prompt, history,
temperature, or max-tokens setting today.

## Retry policy

A provider that is briefly overloaded should not fail a whole multi-agent
pipeline run, so model calls are retried — a few times, only when a retry can
help, and never in a way that sends the same text twice. `llm/retry.py` holds
the policy once; both call paths use it: the direct provider above (pipeline
planning, the CLI) and the LangChain models in `agent_models.py` (chat and
pipeline steps).

- **What is retried:** a connection that failed or dropped before the provider
  answered, and the statuses 408, 429, 500, 502, 503 and 504.
- **What is not:** every other status — a 400, 401, 403, 404 or 422 will fail
  the same way again — and a request that ran into `LLM_TIMEOUT_SECONDS`. That
  timeout is an hour by default, so retrying it could multiply the wait instead
  of shortening it. MCP and built-in tool calls are never retried: they may not
  be idempotent, and a tool that saves a file or calls an API must not run
  twice.
- **How often:** at most `LLM_MAX_RETRIES` retries (default 2, so three
  attempts at most; 0 turns retries off).
- **How long between attempts:** the provider's `Retry-After`, in seconds or as
  an HTTP date, when it sent one. Otherwise a random wait between 0 and
  `LLM_RETRY_BASE_DELAY_SECONDS × 2ⁿ` before retry *n* (counting from 0) —
  exponential backoff with full jitter, so many failed runs do not retry in
  step. Either way never longer than `LLM_RETRY_MAX_DELAY_SECONDS`. With the
  defaults (1 s and 20 s) a call waits at most 40 s in total; an agent step
  stays bounded by `AGENT_TIMEOUT_SECONDS` as a whole.
- **Streams:** retried only until the first piece of output arrives. Text the
  user may already see is never produced a second time; a failure after that
  point ends the stream with the usual error.
- **Afterwards:** the last failure surfaces exactly as it would without
  retries — `ProviderTimeout` or `ProviderRequestError` from the direct
  provider, the SDK's own exception from an agent model, which
  `api/services/agent_runtime.as_agent_error` maps as before.
- **Logs:** each retry is one WARNING,
  `llm.retry provider=openrouter model=<id> attempt=1/3 reason=http_429 delay_s=0.73`.
  The reason is `http_<status>` or the connection error's class name. The
  prompt and the API key are never logged.

**The SDKs' own retries are off**, because none of them can express this
policy (checked against the installed sources):

- `openai` (direct providers and `ChatTogether`): would also retry timeouts,
  409 and every 5xx, obey a nonstandard `x-should-retry` header, use a fixed
  0.5–8 s backoff with partial jitter, and give up instead of waiting when
  `Retry-After` exceeds two minutes. Built with `max_retries=0`.
- `openrouter` SDK (under `ChatOpenRouter`): bounds retries by elapsed time
  rather than count, retries timeouts together with connection errors, and uses
  `Retry-After` uncapped. And with `max_retries=0`, `ChatOpenRouter` merely
  omits its retry config — the SDK then falls back to its default: 5xx,
  connection errors and timeouts retried for up to an hour.
  `RetryingChatOpenRouter._build_client` sets `retry_config=None`, which
  switches it off.

`agent_models.RetryingChatModel` is mixed in ahead of each LangChain
integration and wraps `_generate`, `_agenerate`, `_stream` and `_astream` — the
four methods every LangChain call ends in. The models keep the default
`streaming=False`, so `_generate` never streams inside a retry.

## How a provider gets built

```
user's Settings  ──┐
  (else .env)     ├► api/services/llm_settings.resolve_profile() → LLMProfile
settings.LLM_PROVIDER ┘    (provider, default model, saved key)
                      ──► api/services/llm.provider_config(profile)  → ProviderConfig
                          (saved key, else the .env key; timeout, base URL and
                           retry policy from .env)
                      ──► registry.create_provider(name, config)
                      ──► FACTORIES[name](config)  → providers/<name>.build()
                      ──► OpenAICompatibleProvider(name, client, config)
```

`deps.llm_profile` resolves the profile once per request: the provider and
default model the user saved on the Settings page, else `LLM_PROVIDER` and its
`.env` default, and the user's decrypted key, if they saved one.
`get_provider(profile)` builds an SDK client for pipeline planning. Chat and pipeline
steps use `get_agent_model()` and the `agent_models.py` registry to construct a
LangChain model for the configured provider; steps pass their selected model id.
LangGraph then orchestrates MCP tool calls. Both model adapters set explicit
request timeouts, switch their SDK's retries off and follow the retry policy.

## The model catalogue

`llm/catalog.py` is the **single source of truth for valid model ids**. Each
provider has a `ModelCatalog` subclass whose class attributes are `ModelInfo`
value objects (`model_id`, capability flags, description). `CATALOGS` maps a
provider name to its catalogue.

It is used in three places, which is why they can never disagree:

1. `PipelineStepIn` and `GenerateRequest` reject ids no catalogue lists.
2. `GET /api/models` serves the user's provider's list to the frontend
   (`useModels`), and `GET /api/llm-settings` every provider's.
3. The planner prompt lists the allowed ids, and `parse_plan` replaces any
   other id with the default.

The default model is the one the user saved for that provider, else
`llm_default_models[provider]` (env), else the first catalogue entry.
`available_model_ids()` puts the default first.

## Usage and cost

`llm/usage.py` counts what every model call of a pipeline step used and cost,
the same way for each provider. LangChain's chat models put the token counts of
each answer in `AIMessage.usage_metadata`; the pieces are:

- `TokenUsage` — a frozen value object: `input_tokens`, `output_tokens`,
  `cost_usd` (USD, `None` when unknown) and `cost_complete` (`False` once some
  tokens went unpriced, which `cost_usd` then leaves out). Two add with `+`.
- `UsageCallback` — a LangChain callback. `metered(model, callback)` returns a
  copy of the step's chat model that reports to it (it rides on the model, not
  on the agent's run config, where a callback never reached the model calls on
  Python 3.10). It prices each finished call and tells a `UsageMeter` port
  *before* a call (`before_call`; raising refuses the call, and the exception
  reaches the agent unchanged) and *after* it (`after_call(usage)`). The
  budget of a run is one such meter (`api/services/run_budget.py`).

### Where the cost of a call comes from

`COST_SOURCES` is tried in order (a Strategy chain); the first that knows wins:

| Source | When |
|---|---|
| What the provider reports it charged | OpenRouter returns `usage.cost` with every answer, "the total amount charged to your account"; `langchain-openrouter` hands it on as `response_metadata["cost"]`. OpenRouter's credits are denominated in US dollars and its API prices are in dollars, so the value is read as USD. Nothing has to be requested: its docs say full usage details are always included, and the older switches for them (`usage: {include: true}`, `stream_options.include_usage`) are deprecated and have no effect. |
| The model's published price | `ModelInfo.price(input, output)`, from `input_price_per_million` and `output_price_per_million`. TogetherAI reports no cost, so its calls are priced this way. |
| Unknown | The call's cost is `None`; its tokens are still counted. |

A reported cost that is negative, not finite or not a number is ignored. A
reported `0` is kept as `0`: a free call is not priced from the catalogue.

### Prices in the catalogue

Prices are filled in only where the provider's own page was read, and each one
carries a comment naming the page and the date. A model without one has an
unknown cost on a provider that does not report it; nothing is ever guessed.

| Provider | Model | Input / output per 1M tokens | Source (checked 2026-10-24) |
|---|---|---|---|
| TogetherAI | `openai/gpt-oss-120b` | $0.15 / $0.60 | together.ai/models/gpt-oss-120b and together.ai/pricing |
| OpenRouter | `nvidia/nemotron-3-super-120b-a12b:free` | $0 / $0 | OpenRouter's "Free variant" docs: `:free` models are free |

The other TogetherAI models have no price here: its pricing page listed neither
Kimi K2 Thinking nor Qwen3 Coder 480B A35B, and showed Llama 4 Maverick only
under fine-tuning, not as a serverless price. The other OpenRouter models need
none, because OpenRouter reports what each call cost. A run on a model with an
unknown cost shows its tokens and "Cost unknown for this model"; only a token
limit can stop it.

Prices change: when a provider's page does, update the `ModelInfo` and its
comment together.

## Recipe: add a model

1. Add a `ModelInfo(...)` attribute to the right class in `llm/catalog.py`,
   using the exact id the provider expects. If you can read its price on the
   provider's own page and the provider does not report each call's cost, fill
   `input_price_per_million` and `output_price_per_million` with a comment
   saying where and when; otherwise leave both out.
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
           max_retries=0,  # the retry policy in llm/retry.py retries instead
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
7. Add a LangChain chat model builder in `llm/agent_models.py` so chat can use
   the provider: a `RetryingChatModel` subclass of the integration, built with
   `retrier=_retrier(NAME, config)` and its SDK's own retries switched off
   (check the SDK's source: an off switch is not always what it seems).
8. `make check`.

If the new SDK is **not** OpenAI-shaped, write a separate adapter class that
implements `LLMProvider` and honours the same error contract, rather than
branching inside `OpenAICompatibleProvider`.

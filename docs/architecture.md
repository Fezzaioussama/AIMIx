# Architecture

## System view

```mermaid
graph LR
    Browser["React SPA<br/>Vite :4200"] -->|"/api/* + Bearer JWT<br/>(proxied in dev)"| Django["Django + DRF<br/>:8000"]
    Django -->|ORM| DB[("SQLite")]
    Django -->|"HTTPS, API key,<br/>LLM_TIMEOUT_SECONDS"| LLM["OpenRouter / TogetherAI"]
```

The backend is a **chokepoint**: it holds the provider API key (the browser never
sees it), validates every model id against a catalogue, and bounds every
outbound call with a timeout.

## Backend layers

```mermaid
graph TD
    urls["api/urls.py<br/>routing only"] --> endpoints
    endpoints["api/endpoints/*<br/>HTTP boundary"] --> serializers["api/serializers/*<br/>contracts"]
    endpoints --> services["api/services/*<br/>business logic"]
    endpoints --> repositories
    serializers --> repositories["api/repositories/*<br/>data access"]
    services --> models["api/models.py"]
    repositories --> models
    services --> llm["llm/*<br/>provider layer (no Django)"]
    services -. raise .-> exceptions["api/exceptions.py<br/>DomainError"]
    exceptions -. mapped by .-> errors["api/errors.py<br/>one error shape"]
```

Rules that keep this shape (full text in [AGENTS.md §2](../AGENTS.md)):

- **Endpoints are thin**: validate with a serializer, call a service or
  repository, return a `Response`. No business `if`s, no prompt building.
- **Services never touch HTTP**: they take and return plain Python values and
  dataclasses, and signal failure by raising a `DomainError`.
- **Only `api/errors.py` builds error responses**, always as
  `{"error": "<code>", "detail": "<message>"}`.
- **`llm/` never imports Django**: it receives a `ProviderConfig` dataclass.
  Only `api/services/llm.py` reads provider settings.
- **Ownership filtering lives in `api/repositories/`**, so "another user's
  pipeline" and "no such pipeline" look identical (404).

## Frontend layers

```mermaid
graph TD
    main["main.tsx<br/>Router + AuthProvider"] --> App["App.tsx<br/>routes + nav"]
    App --> features["features/&lt;feature&gt;/<br/>pages + use*.ts hooks"]
    features --> coreapi["core/api/<br/>client.ts gateway, endpoints, types"]
    features --> coreauth["core/auth/<br/>AuthContext, RequireAuth"]
    features --> corehooks["core/hooks/useModels"]
    coreapi --> tokens["core/auth/tokenStorage<br/>sole localStorage owner"]
    coreauth --> tokens
```

Components render and handle input. `fetch`, the bearer token, timeouts, and
error mapping live in `core/api/client.ts`; feature state lives in a
`use<Feature>.ts` hook next to the page.

## Request traces

### 1. Run a pipeline — `POST /api/pipelines/<id>/run`

```mermaid
sequenceDiagram
    participant UI as usePipelineBuilder
    participant C as core/api/client.ts
    participant E as endpoints/pipelines.run_pipeline
    participant R as repositories/pipelines
    participant S as services/pipelines.run
    participant P as llm OpenAICompatibleProvider
    UI->>C: runPipeline(id, input) (timeout 180 s)
    C->>E: POST + Bearer token
    E->>E: RunPipelineSerializer validates {"input"}
    E->>R: get_owned(user, id)
    R-->>E: Pipeline or raise NotFound (404)
    E->>S: ensure_runnable() then run(pipeline, get_provider(), input)
    loop each step, ordered by `order`
        S->>S: step_prompt(template, current)
        S->>P: generate(prompt, step.model)
        P-->>S: text, or ProviderTimeout / ProviderRequestError
        S->>S: current = output
    end
    S-->>E: RunResult dataclass
    E-->>C: 200 asdict(RunResult)
    C-->>UI: PipelineRunResponse
```

A provider error inside the loop is converted by
`api/services/errors.as_domain_error` (e.g. `ProviderTimeout` →
`ProviderTimedOut`, 504) and the whole run fails; there are no partial results.

### 2. Stream chat — `POST /api/chat`

1. `useChatStream.send` adds the user message and an empty AI message, then
   iterates `streamChatReply()` → `client.streamText()`, which reads
   `response.body.getReader()` and yields decoded chunks.
2. `endpoints/chat.chat_view` validates `{"prompt"}` and calls
   `services/chat.stream_reply(provider, prompt)`.
3. `stream_reply` **pulls the first chunk eagerly**. If the provider fails before
   producing anything, a `DomainError` is raised while the response is still
   uncommitted, so the client gets a real 5xx with the standard error body.
4. After the first chunk the response is a `StreamingHttpResponse`
   (`text/plain`). A failure mid-stream can no longer change the status, so it is
   logged (`chat.stream_interrupted`) and the stream simply ends.
5. The hook appends each chunk to the AI message; unmounting aborts the fetch.

### 3. Generate a pipeline — `POST /api/pipelines/generate`

1. `GeneratePipelineSerializer` validates `description` and an optional
   `planner_model` (defaults to the configured default model).
2. `services/pipelines.generate` builds the planner prompt with
   `prompts.pipeline_generation_prompt` (it lists the allowed model ids) and
   calls the provider.
3. `parse_plan` extracts the first `{...}` block, parses JSON, requires `name`
   and a non-empty `steps` list, fills a missing `order`, and **replaces any
   model id not in the catalogue with the default model**. Unusable output →
   `upstream_response_invalid` (502).
4. The endpoint returns the plan **without saving it**. The user edits it in
   `AutoPipelinePage` and saves through the normal `POST /api/pipelines/`.

## Error flow

```
llm/ raises LLMError subclass
  → services translate via api/services/errors.PROVIDER_ERROR_MAP
  → DomainError (code + status) propagates out of the endpoint
  → DRF calls api/errors.exception_handler
  → {"error": code, "detail": message} with the mapped status
  → core/api/client.ts turns it into ApiError(message, status, code)
```

DRF's own errors (validation, 401, 403, 404, 405, ...) go through the same
handler and are mapped by `STATUS_CODES` in `api/errors.py`. An unexpected
exception is **not** caught: Django returns a 500 — never a 200 with an error
inside.

## Design patterns in use

| Pattern | Where | Why |
|---|---|---|
| Registry + Factory | `llm/registry.py`, `api/services/llm.get_provider` | New provider = one dict entry, no `if` chain |
| Adapter | `llm/base.OpenAICompatibleProvider` | Wraps both SDKs behind one contract and one error set |
| Strategy map | `api/services/errors.PROVIDER_ERROR_MAP` | Provider error → domain error, in one place |
| Repository | `api/repositories/pipelines.py` | Ownership-scoped queries and atomic writes |
| Builder | `api/services/prompts.py` | Prompt text kept apart from transport |
| DTO / Value Object | `StepResult`, `RunResult`, `ProviderConfig`, `ModelInfo` | Frozen dataclasses across layers |
| Gateway | `frontend/src/core/api/client.ts` | Token, timeout, error mapping in one place |
| Provider/Context | `frontend/src/core/auth/AuthContext.tsx` | Shared auth state |

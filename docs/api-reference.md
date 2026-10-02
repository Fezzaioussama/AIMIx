# API reference

Base path: `/api`. JSON in and out, except `POST /chat` which streams plain text.

**Auth:** every endpoint requires `Authorization: Bearer <access>` unless marked
**public**. Routes are protected by default (`PROTECTED_ROUTERS` in
`api/routes.py`); a missing, invalid or expired token is `401 not_authenticated`
with `WWW-Authenticate: Bearer`.

Outside production the OpenAPI schema is served at `/api/openapi.json` and an
interactive explorer at `/api/docs`.

**Errors:** every error body is `{"error": "<code>", "detail": "<message>"}`.
The code list is in the [README error contract](../README.md#error-contract);
other codes you may see are `method_not_allowed` (405) and `server_error` (500,
an unexpected failure). A validation error's `detail` lists each problem as
`field: message`, e.g. `"steps.0.model: Unknown model 'x'. Choose one of: ..."`.

---

## Auth

### `POST /register` — public

```json
{ "username": "alice", "password": "a-long-pass-123" }
```

`201` → `{ "username": "alice" }`. The username is up to 150 letters, digits and
`@ . + - _`. The password must pass the same rules the Django version applied
(at least 8 characters, not a common password, not all numeric, not similar to
the username) or a `400 validation_error` lists what is wrong. A taken username
is also a `400`.

### `POST /login` — public

```json
{ "username": "alice", "password": "a-long-pass-123" }
```

`200` → `{ "access": "<jwt>", "refresh": "<jwt>" }`. Wrong credentials → `401`.
Lifetimes: `JWT_ACCESS_MINUTES` (60), `JWT_REFRESH_DAYS` (1).

### `POST /token/refresh` — public

`{ "refresh": "<jwt>" }` → `{ "access": "<jwt>" }`.

### `GET /protected`

`200` → `{ "message": "Hello alice, your token is valid.", "user_id": 1 }`.

---

## Models

### `GET /models`

```json
{ "models": ["deepseek/deepseek-v4-flash", "qwen/qwen3-coder", "..."],
  "default": "deepseek/deepseek-v4-flash" }
```

The ids of the **active provider's** catalogue, default first. These are the
only values accepted for a step's `model` or a `planner_model`.

---

## Agent tools

### `GET /agent-tools`

`200` → an array of tools currently available to pipeline steps:

```json
[
  { "name": "list_pipelines", "description": "List your saved AIMIx pipelines...", "source": "AIMIx" },
  { "name": "inspect_pipeline", "description": "Inspect one of your saved AIMIx pipelines...", "source": "AIMIx" }
]
```

Configured MCP tools also appear with `source: "MCP"` and names prefixed by
their server name. Use the exact `name` values in a step's `allowed_tools`.
Descriptions may be shortened by `AGENT_TOOL_DESCRIPTION_MAX_CHARS`. If a
configured MCP server is unavailable, discovery returns `502 tool_unavailable`.
Pipeline steps cannot call the chat-only `run_pipeline` function.

---

## Chat

### `POST /chat`

```json
{ "prompt": "Explain JWT in two sentences." }
```

`200`, `Content-Type: text/plain; charset=utf-8`, agent answer streamed in
chunks. The agent can call `list_pipelines()`, `inspect_pipeline(pipeline_id)`,
and `run_pipeline(pipeline_id, input_text)` for the signed-in user. LangGraph
also loads all tools from `MCP_SERVERS` and keeps tool output out of the text
stream. The configured provider supplies the model;
there is no conversation history across requests.

A provider or MCP failure **before** the first text chunk returns a normal
error status (502/503/504), including `502 tool_unavailable` if an MCP server
cannot be reached. A failure **after** streaming starts is logged and ends
the stream.

---

## Pipelines

A pipeline object:

```json
{
  "id": 7,
  "name": "Summarise then translate",
  "user": 1,
  "created_at": "2026-09-27T10:00:00Z",
  "steps": [
    { "id": 12, "order": 1, "stage": 1, "title": "Summary", "role": "Summariser", "allowed_tools": [], "is_output": false, "prompt": "Summarise:\n{input}", "model": "deepseek/deepseek-v4-flash" },
    { "id": 13, "order": 2, "stage": 2, "title": "French summary", "role": "Translator", "allowed_tools": null, "is_output": true, "prompt": "Translate to French:\n{input}", "model": "openai/gpt-oss-120b" }
  ]
}
```

`user`, `created_at`, and the step `id`s are read-only. `steps` must contain at
least one step; each `model` must be in `GET /models`. `order` must be unique
within a pipeline (a repeated `order` is a `400 validation_error`).

`stage` (integer ≥ 1, optional, defaults to the step's `order`) sets how steps
run. Stages run one after another in ascending order; **steps that share a stage
run in parallel** on the same input. Giving every step its own stage is a plain
sequential chain.

On a run, each step is a LangGraph agent using its selected `model`. Its optional
`role` (up to 100 characters, default `""`) gives the agent a specialty.
`allowed_tools` controls its tool access:

| Value | Access |
|---|---|
| `null` or omitted | All currently configured pipeline tools (the default) |
| `[]` | No tools |
| `["list_pipelines", "..."]` | Only the exact named tools returned by `GET /agent-tools` |

Names in an explicit list must be non-blank and unique. If a selected tool is
no longer available when the step runs, the run stops with `502 tool_unavailable`.
The native pipeline tools are scoped to the signed-in user; MCP servers come
from `MCP_SERVERS`. A step cannot start another pipeline run. Existing steps
receive `role: ""` and `allowed_tools: null` when the migration is applied.

`title` (optional, ≤ 100 characters) names the step in the UI. `is_output`
(optional, default `false`) marks a step whose result is a **pipeline output**
rather than intermediate work; a pipeline can have several, in any stage, and
an output step still feeds the next stage. When no step is marked, the last
stage's steps are the outputs.

### `GET /pipelines/`

The caller's pipelines, newest first (no pagination).

### `POST /pipelines/`

Body: `name` and `steps` (without ids). `201` → the created pipeline.

### `GET /pipelines/<id>/`

One owned pipeline, or `404 not_found` if it is missing **or owned by someone
else**.

### `PUT /pipelines/<id>/` and `PATCH /pipelines/<id>/`

Rename and/or replace steps. When `steps` is sent, **all existing steps are
deleted and recreated** in one transaction.

### `DELETE /pipelines/<id>/`

`204`. Steps are deleted by cascade.

### `POST /pipelines/<id>/run`

```json
{ "input": "Long article text..." }
```

`200`:

```json
{
  "pipeline_name": "Summarise then translate",
  "final_output": "Résumé ...",
  "intermediate_results": [
    { "step_order": 1, "stage": 1, "title": "Summary", "model": "deepseek/deepseek-v4-flash", "input_used": "Long article text...", "output": "Summary ...", "is_output": false, "tool_calls": [] },
    { "step_order": 2, "stage": 2, "title": "French summary", "model": "openai/gpt-oss-120b", "input_used": "Summary ...", "output": "Résumé ...", "is_output": true, "tool_calls": [{ "name": "list_pipelines", "status": "success" }] }
  ]
}
```

`intermediate_results` holds every step's output, ordered by stage then `order`;
`is_output` is `true` on the results that are the pipeline's outputs (the marked
steps, or the last stage when none is marked).
`tool_calls` records only each called tool's name and `success`/`error` status;
it does not include arguments, tool results, or a durable execution trace.
Each step's prompt has `{input}` replaced by its stage's input; if the template
has no `{input}`, the value is appended as `"\n\nInput: <value>"`.

A stage's input is the previous stage's output. When that stage ran several
steps in parallel, their outputs are joined, each under a
`## Output of step <order>` heading. `final_output` is the last stage's output,
joined the same way if it is parallel; it is kept for compatibility, and the
UI shows the `is_output` results instead. At most `PIPELINE_MAX_PARALLEL_STEPS`
(default 4) steps of one stage run agents at once; if any of them fails,
the run fails.
Errors: `404` not owned, `400 validation_error` if the pipeline has no steps,
`502/503/504` agent or tool failures (the run stops; no partial result is returned).

The call is synchronous: it takes as long as its stages combined, and a parallel
stage takes as long as its slowest step. The frontend waits up to one hour
(`GENERATION_TIMEOUT_MS`). Runs are not persisted or resumable and tool actions
have no approval flow.

### `POST /pipelines/generate`

```json
{ "description": "Take a product review, extract pros and cons, then write a reply.",
  "planner_model": "openai/gpt-oss-120b" }
```

`planner_model` is optional (defaults to the default model). `200`:

```json
{
  "generated_pipeline": {
    "name": "Review responder",
    "steps": [
      { "order": 1, "stage": 1, "title": "Pros", "role": "Analyst", "allowed_tools": [], "is_output": false, "prompt": "List the pros in: {input}", "model": "deepseek/deepseek-v4-flash" },
      { "order": 2, "stage": 1, "title": "Cons", "role": "Analyst", "allowed_tools": [], "is_output": false, "prompt": "List the cons in: {input}", "model": "deepseek/deepseek-v4-flash" },
      { "order": 3, "stage": 2, "title": "Reply", "role": "Writer", "allowed_tools": [], "is_output": true, "prompt": "Write a polite reply based on: {input}", "model": "deepseek/deepseek-v4-flash" }
    ]
  },
  "available_models": ["deepseek/deepseek-v4-flash", "..."]
}
```

Nothing is saved. Before planning, AIMIx discovers the same pipeline tool
catalogue as `GET /agent-tools` and gives its names and descriptions to the
planner. The planner chooses roles and tool allowlists for its steps. Unknown
tool names are removed from explicit allowlists; repeated names are deduplicated.
If the planner omits an allowlist or does not return a list, it becomes `null`
(all tools). Unknown model ids are replaced by the default, `order` is
renumbered 1..N, a missing or invalid `stage` falls back to the step's position
(sequential), a missing `title` or `role` becomes `""`, and any `is_output`
other than `true` becomes `false`.
If the planner's answer has no usable JSON: `502 upstream_response_invalid`.

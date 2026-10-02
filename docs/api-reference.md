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
    { "id": 12, "order": 1, "stage": 1, "title": "Summary", "is_output": false, "prompt": "Summarise:\n{input}", "model": "deepseek/deepseek-v4-flash" },
    { "id": 13, "order": 2, "stage": 2, "title": "French summary", "is_output": true, "prompt": "Translate to French:\n{input}", "model": "openai/gpt-oss-120b" }
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
    { "step_order": 1, "stage": 1, "title": "Summary", "model": "deepseek/deepseek-v4-flash", "input_used": "Long article text...", "output": "Summary ...", "is_output": false },
    { "step_order": 2, "stage": 2, "title": "French summary", "model": "openai/gpt-oss-120b", "input_used": "Summary ...", "output": "Résumé ...", "is_output": true }
  ]
}
```

`intermediate_results` holds every step's output, ordered by stage then `order`;
`is_output` is `true` on the results that are the pipeline's outputs (the marked
steps, or the last stage when none is marked).
Each step's prompt has `{input}` replaced by its stage's input; if the template
has no `{input}`, the value is appended as `"\n\nInput: <value>"`.

A stage's input is the previous stage's output. When that stage ran several
steps in parallel, their outputs are joined, each under a
`## Output of step <order>` heading. `final_output` is the last stage's output,
joined the same way if it is parallel; it is kept for compatibility, and the
UI shows the `is_output` results instead. At most `PIPELINE_MAX_PARALLEL_STEPS`
(default 4) steps of one stage call the provider at once; if any of them fails,
the run fails.
Errors: `404` not owned, `400 validation_error` if the pipeline has no steps,
`502/503/504` provider failures (the run stops; no partial result is returned).

The call is synchronous: it takes as long as its stages combined, and a parallel
stage takes as long as its slowest step. The frontend waits up to one hour
(`GENERATION_TIMEOUT_MS`).

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
      { "order": 1, "stage": 1, "title": "Pros", "is_output": false, "prompt": "List the pros in: {input}", "model": "deepseek/deepseek-v4-flash" },
      { "order": 2, "stage": 1, "title": "Cons", "is_output": false, "prompt": "List the cons in: {input}", "model": "deepseek/deepseek-v4-flash" },
      { "order": 3, "stage": 2, "title": "Reply", "is_output": true, "prompt": "Write a polite reply based on: {input}", "model": "deepseek/deepseek-v4-flash" }
    ]
  },
  "available_models": ["deepseek/deepseek-v4-flash", "..."]
}
```

Nothing is saved. The planner decides which steps can run in parallel by giving
them the same `stage`. Unknown model ids in the plan are replaced by the
default, `order` is renumbered 1..N, a missing or invalid `stage` falls back
to the step's position (sequential), a missing `title` becomes `""`, and any
`is_output` other than `true` becomes `false`.
If the planner's answer has no usable JSON: `502 upstream_response_invalid`.

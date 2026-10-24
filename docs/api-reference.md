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
is also a `400`. Production deployments must explicitly enable public sign-up
with `ALLOW_PUBLIC_REGISTRATION=true`; otherwise this endpoint returns `403`.

### `POST /login` — public

```json
{ "username": "alice", "password": "a-long-pass-123" }
```

`200` → `{ "access": "<jwt>" }` and sets the refresh token in an `HttpOnly`,
`SameSite=Strict` cookie. JavaScript and browser storage never receive the
refresh token. Wrong credentials → `401`. Lifetimes: `JWT_ACCESS_MINUTES` (60),
`JWT_REFRESH_DAYS` (1).

### `POST /token/refresh` — public

No request body. The refresh cookie is rotated and the previous token becomes
invalid. `200` → `{ "access": "<jwt>" }` plus the replacement refresh cookie.

### `POST /token/logout` — public

Revokes the presented refresh cookie and clears it. Idempotent; returns `204`.

All public authentication operations are limited per client and operation by
`AUTH_RATE_LIMIT_REQUESTS` / `AUTH_RATE_LIMIT_WINDOW_SECONDS`; excess requests
return `429 throttled` with `Retry-After`.

### `GET /protected`

`200` → `{ "message": "Hello alice, your token is valid.", "user_id": 1 }`.

---

## Health

### `GET /health` — public

`200 {"status": "ok"}` while the process serves requests. Used by Railway's
health check (`railway.json`).

---

## Models

### `GET /models`

```json
{ "models": ["deepseek/deepseek-v4-flash", "qwen/qwen3-coder", "..."],
  "default": "deepseek/deepseek-v4-flash" }
```

The ids of **your provider's** catalogue, your default first — the provider and
default chosen on the Settings page (`/llm-settings`), else `LLM_PROVIDER` and
its default from `backend/.env`. Offer these for a step's `model` or a
`planner_model`. Requests accept any catalogued id; one from another provider's
catalogue is rejected by that provider when the step runs.

`503 provider_not_configured` when your saved key can no longer be decrypted
(the server's `SECRET_KEY` changed): enter it again on the Settings page.

---

## LLM settings

Per account. What you save here overrides `backend/.env` for your requests
only; anything you leave unset falls back to it. Keys are stored encrypted
(Fernet, keyed from `SECRET_KEY`) and are **never returned** — only their last
four characters.

### `GET /llm-settings`

```json
{
  "provider": "openrouter",
  "providers": [
    { "name": "openrouter", "key_source": "saved", "key_hint": "9876",
      "default_model": "x-ai/grok-4.20", "models": ["x-ai/grok-4.20", "..."] },
    { "name": "togetherai", "key_source": "environment", "key_hint": "",
      "default_model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8", "models": ["..."] }
  ]
}
```

`key_source` is `saved` (yours), `environment` (the server's `backend/.env`) or
`none`. `models` is that provider's catalogue, its default first.

### `PUT /llm-settings`

```json
{ "provider": "openrouter",
  "providers": [{ "name": "openrouter", "default_model": "x-ai/grok-4.20", "api_key": "sk-or-..." }] }
```

Sets the active provider and updates only the providers listed. Omit
`api_key` (or send `null`) to keep the saved key. `200` returns the same shape
as `GET`. `400 validation_error` for an unknown provider, a provider listed
twice, a `default_model` outside that provider's catalogue, or a blank key or
one containing spaces. Saving the same body twice leaves the same state.

### `DELETE /llm-settings/keys/<provider>`

Forgets your saved key for that provider, which then falls back to the
server's key, if any. Idempotent. `200` returns the same shape as `GET`.

---

## Agent tools

### `GET /agent-tools`

`200` → an array of tools currently available to pipeline steps:

```json
[
  { "name": "list_pipelines", "description": "List your saved AIMIx pipelines...", "source": "AIMIx" },
  { "name": "inspect_pipeline", "description": "Inspect one of your saved AIMIx pipelines...", "source": "AIMIx" },
  { "name": "web_search", "description": "Search the web for current information...", "source": "AIMIx" },
  { "name": "fetch_url", "description": "Read a public web page...", "source": "AIMIx" },
  { "name": "calculator", "description": "Evaluate an arithmetic expression reliably...", "source": "AIMIx" },
  { "name": "current_datetime", "description": "Return the current date and time in UTC...", "source": "AIMIx" },
  { "name": "list_workspace_files", "description": "List visible local workspace files...", "source": "AIMIx" },
  { "name": "read_workspace_file", "description": "Read a bounded local text file...", "source": "AIMIx" },
  { "name": "search_workspace_files", "description": "Search local text files...", "source": "AIMIx" },
  { "name": "read_csv", "description": "Read a local CSV as structured rows...", "source": "AIMIx" },
  { "name": "save_artifact", "description": "Save a new local deliverable...", "source": "AIMIx" },
  { "name": "run_python", "description": "Run Python in a fresh sandbox without internet...", "source": "AIMIx" }
]
```

The built-in tools are the ones enabled by `AGENT_BUILTIN_TOOLS`; `web_search`
is listed only when `TAVILY_API_KEY` is set, and `run_python` only when
`E2B_API_KEY` is set. Configured MCP tools also appear with `source: "MCP"` and names prefixed by
their server name. Use the exact `name` values in a step's `allowed_tools`.
Descriptions may be shortened by `AGENT_TOOL_DESCRIPTION_MAX_CHARS`. If a
configured MCP server is unavailable, discovery returns `502 tool_unavailable`.
Pipeline steps cannot call the chat-only `run_pipeline` function.

The five workspace tools are confined to a private
`AGENT_WORKSPACE_DIR/user-<id>` directory. They reject absolute, parent and hidden paths; reads,
searches and CSV rows are bounded by the `WORKSPACE_*` settings. `save_artifact`
accepts only `.txt`, `.md`, `.json` and `.csv` and never overwrites an existing
file. When any workspace-reading tool is enabled, outbound `web_search` and
`fetch_url` are suppressed unless `AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS=true`
explicitly accepts the data-exfiltration risk.

`run_python` takes `code` and optional `input_files` (workspace paths, under the
same rules, copied to `/home/user/inputs/`). Each call runs in a fresh E2B
sandbox without internet access. Files the code writes to `/home/user/outputs/`
and the PNG charts it displays are saved to `sandbox/<UTC time>/` in the
workspace, never overwriting. It counts as a workspace reader for the rule
above. A failure in the code, a timeout or an unavailable sandbox is an `error`
tool call that the agent can react to.

---

## Chat

### `POST /chat`

```json
{ "prompt": "Explain JWT in two sentences." }
```

`200`, `Content-Type: text/plain; charset=utf-8`, agent answer streamed in
chunks. The agent can call `list_pipelines()`, `inspect_pipeline(pipeline_id)`
(which lists a pipeline's named inputs), and `run_pipeline(pipeline_id,
input_text, inputs)` for the signed-in user; `inputs` holds the values of a
pipeline's named inputs, under the same rules as a run request. LangGraph
also loads all tools from `MCP_SERVERS` and keeps tool output out of the text
stream. The configured provider supplies the model;
there is no conversation history across requests.

A provider or MCP failure **before** the first text chunk returns a normal
error status (502/503/504), including `502 tool_unavailable` if an MCP server
cannot be reached. A failure **after** streaming starts is logged and ends
the stream.

---

## Documents

### `POST /documents/extract`

Reads an uploaded file and returns its text, so a document can be a pipeline
run's input. `multipart/form-data` with one `file` field. Nothing is stored: the
client puts the returned `text` in a run input (see `POST /pipelines/<id>/run`).

Supported by extension (case-insensitive): `.pdf`, `.docx`, `.html`, `.htm`, and
plain text: `.txt`, `.md`, `.markdown`, `.csv`, `.tsv`, `.json`, `.yaml`, `.yml`,
`.xml`, `.log`, `.rst`. A PDF is read page by page; a Word file keeps its tables
in place (`a | b` per row); HTML keeps visible text only; text is decoded as
UTF-8 (BOM, UTF-16 and Windows-1252 are handled).

`200`:

```json
{
  "filename": "report.pdf",
  "format": "pdf",
  "text": "Quarterly report: revenue grew by ten percent\n\nSecond page: ...",
  "characters": 75,
  "pages": 2,
  "truncated": false
}
```

`pages` is `null` for formats without pages. `truncated` is `true` when part of
the document was left out (more than `DOCUMENT_MAX_PAGES` pages, or more than
`DOCUMENT_MAX_CHARS` characters of text); the returned `text` then ends with
`[Document truncated: the rest was not included.]` so the model knows too.

| Status | `error` | When |
|---|---|---|
| 400 | `validation_error` | No `file` field |
| 401 | `not_authenticated` | No or invalid token |
| 413 | `document_too_large` | The file is over `DOCUMENT_MAX_BYTES` (10 MB). A request whose declared `Content-Length` is over that plus 1 MB is refused earlier, before it is read, as `request_too_large` |
| 415 | `unsupported_document` | The extension is not supported; `detail` lists the supported ones |
| 422 | `document_unreadable` | Empty, password-protected PDF, damaged or not really that format, a `.docx` that unpacks past `DOCUMENT_MAX_UNPACKED_BYTES`, or no text at all (a scanned PDF or image needs OCR, which is not supported) |

Limits are per request and come from settings (see `backend/.env.example`).
The file's name and content are never logged.

## Pipelines

A pipeline object:

```json
{
  "id": 7,
  "name": "Summarise then translate",
  "user": 1,
  "created_at": "2026-09-27T10:00:00Z",
  "inputs": [
    { "name": "article", "label": "Article", "description": "The text to summarise" },
    { "name": "language", "label": "Target language", "description": "e.g. French" }
  ],
  "steps": [
    { "id": 12, "order": 1, "stage": 1, "title": "Summary", "role": "Summariser", "allowed_tools": [], "is_output": false, "expected_output": "Five bullet points", "prompt": "Summarise:\n{article}", "model": "deepseek/deepseek-v4-flash" },
    { "id": 13, "order": 2, "stage": 2, "title": "Translated summary", "role": "Translator", "allowed_tools": null, "is_output": true, "expected_output": "The bullets, translated", "prompt": "Translate to {language}:\n{input}", "model": "openai/gpt-oss-120b" }
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
from `MCP_SERVERS`. When a built-in tool fails during a step (for example
`fetch_url` on a private address or a page that times out), the agent receives
the error and the run continues; the call appears in `tool_calls` with
`status: "error"`. A step cannot start another pipeline run. Existing steps
receive `role: ""` and `allowed_tools: null` when the migration is applied.

`title` (optional, ≤ 100 characters) names the step in the UI. `is_output`
(optional, default `false`) marks a step whose result is a **pipeline output**
rather than intermediate work; a pipeline can have several, in any stage, and
an output step still feeds the next stage. When no step is marked, the last
stage's steps are the outputs. `expected_output` (optional, ≤ 500 characters,
default `""`) says what the step's agent must deliver, in content and format;
it is added to the agent's system prompt. Existing steps get `""` when the
migration is applied.

`inputs` (optional, default `[]`, at most 20) declares the **named values every
run is given**, in the order the run form shows them. Each has a `name`, an
optional `label` (≤ 100 characters, shown on the run form; the UI falls back to
the name) and `description` (≤ 300 characters, telling the user what to
enter). A `name` starts with a lowercase letter, uses only `a-z`, `0-9` and
`_`, has at most 40 characters, is unique within the pipeline and is never
`input` (`{input}` is each stage's input). Any step, **in any stage**, inserts
a value with `{name}`, so later stages still see the original request. With
`inputs: []` the pipeline runs on one free-text input, as pipelines saved
before named inputs existed do.

### `GET /pipelines/`

The caller's pipelines, newest first (no pagination).

### `POST /pipelines/`

Body: `name` and `steps` (without ids). `201` → the created pipeline.

### `GET /pipelines/<id>/`

One owned pipeline, or `404 not_found` if it is missing **or owned by someone
else**.

### `PUT /pipelines/<id>/` and `PATCH /pipelines/<id>/`

Rename, redeclare the inputs and/or replace steps. When `steps` is sent, **all
existing steps are deleted and recreated** in one transaction. `PUT` replaces
the whole pipeline, so leaving out `inputs` clears them; `PATCH` keeps every
field it does not send.

### `DELETE /pipelines/<id>/`

`204`. Steps are deleted by cascade.

### `POST /pipelines/<id>/run`

A pipeline without named inputs runs on free text:

```json
{ "input": "Long article text..." }
```

A pipeline that declares `inputs` takes a non-blank value for **each** of them,
and nothing else:

```json
{ "inputs": { "article": "Long article text...", "language": "French" } }
```

A value may be the text of a document: have `POST /documents/extract` read the
file and send what it returns as the value. The run API itself only ever sees text.

Sending text to a pipeline with named inputs, named values to one without, a
blank value, or a name the pipeline does not declare is a `400
validation_error` whose `detail` names the problem; no agent runs. Both
fields are trimmed.

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
Each step's prompt has `{input}` replaced by its stage's input and `{name}` by
the run's value for that named input, in one pass (a substituted value is
never expanded again; braces that name nothing are left as written). If the
template does not place its stage's input, the value is appended as
`"\n\nInput: <value>"`. In the first stage, whose input is the named inputs
themselves, using any `{name}` counts as placing it.

The first stage's input is the run's text, or its named values: one value as
it is, several each under a `## <label>` heading. A later stage's input is the
previous stage's output. When that stage ran several steps in parallel, their
outputs are joined, each under a `## Output of step <order>` heading. `final_output` is the last stage's output,
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

`planner_model` is optional (defaults to your default model). `200`:

```json
{
  "generated_pipeline": {
    "name": "Review responder",
    "inputs": [
      { "name": "review", "label": "Product review", "description": "The review to answer" }
    ],
    "steps": [
      { "order": 1, "stage": 1, "title": "Pros", "role": "Analyst", "allowed_tools": [], "is_output": false, "expected_output": "A bullet list of pros", "prompt": "List the pros in: {review}", "model": "deepseek/deepseek-v4-flash" },
      { "order": 2, "stage": 1, "title": "Cons", "role": "Analyst", "allowed_tools": [], "is_output": false, "expected_output": "A bullet list of cons", "prompt": "List the cons in: {review}", "model": "deepseek/deepseek-v4-flash" },
      { "order": 3, "stage": 2, "title": "Reply", "role": "Writer", "allowed_tools": [], "is_output": true, "expected_output": "A polite reply under 120 words", "prompt": "Reply to {review} using: {input}", "model": "deepseek/deepseek-v4-flash" }
    ]
  },
  "available_models": ["deepseek/deepseek-v4-flash", "..."]
}
```

Nothing is saved. Before planning, AIMIx discovers the same pipeline tool
catalogue as `GET /agent-tools` and gives its names and descriptions to the
planner. The planner declares the run's named `inputs` and chooses roles,
expected outputs and tool allowlists for its steps. Unknown tool names are
removed from explicit allowlists; repeated names are deduplicated. If the
planner omits an allowlist or does not return a list, it becomes `null` (all
tools). Unknown model ids are replaced by the default, `order` is renumbered
1..N, a missing or invalid `stage` falls back to the step's position
(sequential), a missing `title`, `role` or `expected_output` becomes `""` (and
a too-long one is cut to its limit), and any `is_output` other than `true`
becomes `false`. Inputs that could not be saved are dropped: entries that are
not objects, or whose `name` is invalid, reserved or already taken. A missing
or non-list `inputs` becomes `[]`.
If the planner's answer has no usable JSON: `502 upstream_response_invalid`.

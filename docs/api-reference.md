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
other codes you may see are `method_not_allowed` (405), `budget_exceeded` (409,
a run reached its [spending limit](#spending-limits)) and `server_error` (500,
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
only; the provider and model you leave unset fall back to it, the key only when
the operator set `ALLOW_SERVER_LLM_KEY=true`. Keys are stored encrypted
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

`key_source` is `saved` (yours), `environment` (the server's `backend/.env`,
reported only with `ALLOW_SERVER_LLM_KEY=true`) or `none`. With `none`, requests
that call a model fail with `503 provider_not_configured`. `models` is that provider's catalogue, its default first.

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
server's key only with `ALLOW_SERVER_LLM_KEY=true`. Idempotent. `200` returns the same shape as `GET`.

---

## Integrations

Your own MCP servers (a CRM, a database, company tools, an automation hub…).
Their tools join the operator's `MCP_SERVERS` for **your** chat and pipeline
agents only, named `<integration name>_<tool name>`. Servers are reached over
streamable HTTP only, never stdio. Header values are stored encrypted (Fernet,
keyed from `SECRET_KEY`) and are **never returned** — only each header's name
and `hint`, the last four characters of a value at least twelve characters
long (empty for a shorter one).

An integration object:

```json
{ "id": 1, "name": "crm", "url": "https://mcp.crm.example/mcp", "enabled": true,
  "require_approval": true,
  "headers": [{ "name": "Authorization", "hint": "1234" }],
  "created_at": "2026-10-24T10:00:00Z" }
```

`require_approval` ("Ask me before its tools act") is `true` unless you switch it
off: in a run, each of the integration's tool calls then waits for your
[approval](#approvals) before it acts. Chat has no run to pause, so it is **not
offered** the tools of an integration that asks first; switch `require_approval`
off to use an integration's tools in chat.

**Address rules** (checked when you save, before a test, and again before
every request agents send): the URL must start with `https` (plain `http` only
when `APP_ENV=local`), may not contain a user name or password, and its host
must resolve only to public addresses — never loopback, private, link-local
(such as the cloud metadata address `169.254.169.254`), shared or reserved
ones. Local development can reach a server on `127.0.0.1` with
`APP_ENV=local` and `INTEGRATIONS_ALLOW_PRIVATE_NETWORK=true`. A refused
address is a `400 validation_error` naming the host.

### `GET /integrations`

Your integrations, oldest first.

### `POST /integrations`

```json
{ "name": "crm", "url": "https://mcp.crm.example/mcp", "enabled": true,
  "headers": [{ "name": "Authorization", "value": "Bearer sk-..." }] }
```

`201` → the integration. `name` is 2–31 characters: a lowercase letter, then
lowercase letters, digits or `_`; it is unique among your integrations and may
not be the name of one of the operator's `MCP_SERVERS`. `enabled` and
`require_approval` default to `true`. `headers` (at most 10) need a value each; names are HTTP header names,
unique ignoring case, and `Host`, `Content-Length`, `Transfer-Encoding`,
`Connection`, `Keep-Alive`, `Upgrade`, `TE`, `Trailer`, `Mcp-Session-Id` and
`Mcp-Protocol-Version` are set automatically. Values may not contain control
characters. You can have up to `INTEGRATIONS_MAX_PER_USER` (10) integrations.
Any rule broken is a `400 validation_error`.

### `PATCH /integrations/<id>`

```json
{ "name": "sales", "enabled": false,
  "headers": [{ "name": "Authorization" }, { "name": "X-Team", "value": "ops" }] }
```

Every field is optional; one left out keeps its value, so `{"enabled": false}`
switches the integration off (agents stop using it) and `{"require_approval":
false}` lets its tools act without asking; both are safe to send twice.
`headers`, when sent, is the complete list: a header left out is removed, and a
header sent **without** a `value` keeps the value saved under that name (`400`
if there is none). Saved values only go to the server they were entered for:
changing the URL's scheme, host or port needs every header value again, else
`400`. `200` → the integration. Renaming changes its tools' names, so steps that
selected them by name need updating.

### `DELETE /integrations/<id>`

`204`. A second call is `404`, as for pipelines.

### `POST /integrations/<id>/test`

Connects within `MCP_TIMEOUT_SECONDS` and lists the server's tools, named as
agents and `allowed_tools` see them (works for a switched-off integration too):

```json
{ "tools": [{ "name": "crm_find_contact", "description": "Find the main contact person at a company." }] }
```

Descriptions are cut to `AGENT_TOOL_DESCRIPTION_MAX_CHARS`. Failures:

| Status | `error` | When |
|---|---|---|
| 400 | `validation_error` | The address is no longer allowed (for example its host now resolves to a private address), the name is now used by an operator server, or the header values can no longer be read because `SECRET_KEY` changed (enter them again) |
| 404 | `not_found` | Not yours, or no such integration |
| 502 | `tool_unavailable` | `detail` says why in plain words: `Could not connect to crm: it refused the sign-in (HTTP 401), so check the headers.`, `… nothing was found at that URL (HTTP 404).`, `… it did not answer within the time limit.`, `… the connection to it failed.`, `… it answered with an MCP error.` |

Every integration route answers `404` for another account's integration.

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
  { "name": "list_workspace_files", "description": "List the files in the user's workspace...", "source": "AIMIx" },
  { "name": "read_workspace_file", "description": "Read a file from the user's workspace...", "source": "AIMIx" },
  { "name": "search_workspace_files", "description": "Search local text files...", "source": "AIMIx" },
  { "name": "read_csv", "description": "Read a local CSV as structured rows...", "source": "AIMIx" },
  { "name": "save_artifact", "description": "Save a new file in the user's workspace...", "source": "AIMIx" },
  { "name": "run_python", "description": "Run Python in a fresh sandbox without internet...", "source": "AIMIx" }
]
```

The built-in tools are the ones enabled by `AGENT_BUILTIN_TOOLS`; `web_search`
is listed only when `TAVILY_API_KEY` is set, and `run_python` only when
`E2B_API_KEY` is set. Configured MCP tools also appear with `source: "MCP"` and names prefixed by
their server name. Tools of your enabled [integrations](#integrations) appear
with the integration's name as `source` (e.g. `"crm"`) and as their name prefix.
Use the exact `name` values in a step's `allowed_tools`.
Descriptions may be shortened by `AGENT_TOOL_DESCRIPTION_MAX_CHARS`. If a
configured MCP server is unavailable, discovery returns `502 tool_unavailable`.
An integration that cannot be reached, or whose address is no longer allowed,
is left out instead (the server logs `integration.discovery_skipped`), so the
list still loads; so is an integration tool whose name another tool already
has or that is not 1–64 letters, digits, `_` or `-`.
Pipeline steps cannot call the chat-only `run_pipeline` function. The list does
not say which tools [ask for approval](#approvals) when a step calls them: that
depends on the source's setting (`MCP_REQUIRE_APPROVAL`, an integration's
`require_approval`, `AGENT_APPROVAL_TOOLS`), not on the tool.

The five workspace tools are confined to a private
`AGENT_WORKSPACE_DIR/user-<id>` directory — the same one the [Files](#files)
endpoints show the user. They reject absolute, parent and hidden paths and never
follow a link; reads, searches and CSV rows are bounded by the `WORKSPACE_*`
settings. `read_workspace_file` returns text, Markdown, JSON, YAML, HTML and CSV
files as written, and PDF and Word (and the other run-document formats) as their
extracted text, cut at `WORKSPACE_MAX_OUTPUT_CHARS`. `save_artifact` writes `.txt`,
`.md`, `.json`, `.csv` and `.html` as given; for `.docx` and `.pdf` the agent
passes Markdown (headings, paragraphs, bullet and numbered lists, bold, italic,
links, tables, code, quotes) and it is laid out as a document. It never
overwrites an existing file, refuses an artifact (or its Markdown) over
`WORKSPACE_MAX_FILE_BYTES`, and refuses one that would take the user's files past
`WORKSPACE_MAX_TOTAL_BYTES`. When any workspace-reading tool is enabled, outbound
`web_search` and `fetch_url` are suppressed unless
`AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS=true` explicitly accepts the
data-exfiltration risk.

`run_python` takes `code` and optional `input_files` (workspace paths, under the
same rules, copied to `/home/user/inputs/`). Each call runs in a fresh E2B
sandbox without internet access. Files the code writes to `/home/user/outputs/`
and the PNG charts it displays are saved to `sandbox/<UTC time>/outputs/` and
`sandbox/<UTC time>/charts/` in the workspace, never overwriting. It counts as
a workspace reader for the rule above, but only when it is offered. A failure in the code, a timeout or an unavailable sandbox is an `error`
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
pipeline's named inputs, under the same rules as a run request. A run started
from chat is recorded in the run history like any other, and its steps ask for
[approval](#approvals) where their tools require it. LangGraph also loads the
tools of `MCP_SERVERS` and of your enabled integrations **that need no
approval**: chat has no run to pause, so a tool that asks first is not offered
to it (`MCP_REQUIRE_APPROVAL=false` and an integration's `require_approval:
false` let their tools act at once, in chat too). Tool output stays out of the
text stream. An integration that cannot be reached is skipped. The configured
provider supplies the model; there is no conversation history across requests.

A provider or MCP failure **before** the first text chunk returns a normal
error status (502/503/504), including `502 tool_unavailable` if an MCP server
cannot be reached. A failure **after** streaming starts is logged and ends
the stream.

---

## Documents

### `POST /documents/extract`

Reads an uploaded file and returns its text, so a document can be a pipeline
run's input. `multipart/form-data` with one `file` field. Nothing is stored: the
client puts the returned `text` in a run input (see `POST /pipelines/<id>/runs`).

Supported by extension (case-insensitive):

| Format | Extensions | What the text holds |
|---|---|---|
| PDF | `.pdf` | Each page's text layer; a page without one is read by OCR (see below) |
| Word | `.docx` | Paragraphs, with tables in place (`a \| b` per row) |
| Excel | `.xlsx` | `## Sheet: <name>`, then each row as tab-separated values. Formulas give their saved value; a sheet is read as it is, not as the size it declares |
| PowerPoint | `.pptx` | Per slide: `## Slide <n>: <title>`, its text, table rows (`a \| b`), grouped shapes, then `Speaker notes: ...` |
| Image | `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`, `.bmp`, `.gif` | Read by OCR. Every page of a TIFF; the first frame of an animated GIF or WebP. Transparency is read as white and an EXIF rotation is applied. The content decides the decoder, so a misnamed photo still reads, but only these decoders ever run |
| HTML | `.html`, `.htm` | Visible text only |
| Text | `.txt`, `.md`, `.markdown`, `.csv`, `.tsv`, `.json`, `.yaml`, `.yml`, `.xml`, `.log`, `.rst` | Decoded as UTF-8 (BOM, UTF-16 and Windows-1252 are handled) |

**OCR** (Tesseract, languages `DOCUMENT_OCR_LANGUAGES`, default English and
French) reads images and the PDF pages that have no text layer; pages with a
text layer are never sent to it. A PDF page is rendered at `DOCUMENT_OCR_DPI`
(300), less if that would exceed `DOCUMENT_MAX_IMAGE_PIXELS`. At most
`DOCUMENT_OCR_MAX_PAGES` (30) pages of one document are recognised, each
within `DOCUMENT_OCR_TIMEOUT_SECONDS` (15). A page past that cap, one that
takes too long or that OCR fails on, or every scanned page when OCR is off or not
installed, is skipped, and the text names it at the end, for example
`[Not read: pages 31-40 (OCR reads at most 30 pages per document).]` or
`[Not read: page 2 (no text layer, and OCR is not available).]`.

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

`pages` is the page count of a PDF, the slide count of a deck or the page
count of a TIFF (counted only up to `DOCUMENT_MAX_PAGES`: counting every page of
a TIFF can take quadratic time), and `null` for other formats. `truncated` is
`true` when part of the document was left out: more than `DOCUMENT_MAX_PAGES`
(300) pages, slides or TIFF pages, more than `DOCUMENT_MAX_SPREADSHEET_ROWS`
(5,000) rows in a workbook (all sheets together, blank rows included) or more
cells than `DOCUMENT_MAX_CHARS` (a row is as wide as its last cell), more than
`DOCUMENT_MAX_CHARS` characters of text, or pages OCR skipped. A cut text ends
with `[Document truncated: the rest was not included.]`, and skipped pages are
named as above, so the model knows too.

| Status | `error` | When |
|---|---|---|
| 400 | `validation_error` | No `file` field |
| 401 | `not_authenticated` | No or invalid token |
| 413 | `document_too_large` | The file is over `DOCUMENT_MAX_BYTES` (10 MB). A request whose declared `Content-Length` is over that plus 1 MB is refused earlier, before it is read, as `request_too_large` |
| 415 | `unsupported_document` | The extension is not supported; `detail` lists the supported ones |
| 422 | `document_unreadable` | Empty, password-protected PDF, damaged or not really that format, a `.docx`, `.xlsx` or `.pptx` that unpacks past `DOCUMENT_MAX_UNPACKED_BYTES` (50 MB), an image (or one TIFF page) over `DOCUMENT_MAX_IMAGE_PIXELS` (40 million) checked before it is decoded, an image while OCR is off or not installed, or no text at all (`detail` then says which pages were skipped and why) |

Limits are per request and come from settings (see `backend/.env.example`).
The file's name and content are never logged.

The call is synchronous. OCR takes about three seconds per dense A4 page on one
CPU, so a long scan can hold the request for a minute or two (at worst
`DOCUMENT_OCR_MAX_PAGES` x `DOCUMENT_OCR_TIMEOUT_SECONDS`); the frontend waits
up to ten minutes (`UPLOAD_TIMEOUT_MS`), longer than that worst case by default.

---

## Files

Each account has one private folder, `AGENT_WORKSPACE_DIR/user-<id>`, shared with
its agents: files the user uploads here are what the workspace tools read, and
what `save_artifact` writes appears here. Paths are relative to that folder and
`/`-separated. Every path is refused (`400 validation_error`) when it is
absolute, contains `..`, names something hidden (any part starting with `.`) or
passes through a link. Another user's file is indistinguishable from a missing
one (`404`). Names and contents are never logged.

### `GET /files`

`200`, the files newest first and the limits that apply:

```json
{
  "files": [
    { "path": "reports/q3.pdf", "size": 48213, "modified_at": "2026-10-24T09:30:00Z", "type": "pdf" },
    { "path": "notes.txt", "size": 5, "modified_at": "2026-10-23T18:02:11Z", "type": "txt" }
  ],
  "used_bytes": 48218,
  "quota_bytes": 100000000,
  "max_file_bytes": 10000000,
  "allowed_extensions": [".csv", ".docx", ".html", ".json", ".md", ".pdf", ".pptx", ".txt", ".xlsx", ".yaml", ".yml"]
}
```

`type` is the lower-case extension without its dot (empty when there is none).
`used_bytes` is the sum of the sizes listed, which is what the quota counts;
hidden files are neither listed nor counted. The list is not paginated.

### `POST /files`

`multipart/form-data` with one or more `files` parts and an optional
`replace` field (`true` to overwrite a file of the same name). `201` → an array
of the stored files, in the shape of `GET /files`'s entries.

Each name is made safe first: only the last part of the browser's name is kept;
control and reserved characters (`/ \ : * ? " < > |`) become `_`; whitespace is
collapsed; leading dots are dropped; the extension is lower-cased and the name is
cut to 255 bytes. `C:\Users\me\Q3 report?.PDF` is stored as `Q3 report_.pdf`.
Names, extensions and sizes are checked for every file before any is written;
a name conflict or the quota is checked as each file is saved, so a refusal
there keeps the files saved before it. The app uploads one file per request.

| Status | `error` | When |
|---|---|---|
| 400 | `validation_error` | No `files` part, a name with nothing left after cleaning, or two files with the same name |
| 409 | `file_exists` | A file has that name and `replace` was not `true` |
| 413 | `file_too_large` | A file is over `DOCUMENT_MAX_BYTES` (10 MB) — the one cap on every upload. A request whose declared `Content-Length` is over that plus 1 MB is refused before it is read, as `request_too_large` |
| 413 | `storage_quota_exceeded` | The user's files would take more than `WORKSPACE_MAX_TOTAL_BYTES` (100 MB) |
| 415 | `unsupported_file_type` | The extension is not in `WORKSPACE_UPLOAD_EXTENSIONS`; `detail` lists the accepted ones |

### `GET /files/<path>`

The file, always as a download: `Content-Disposition: attachment` with the file's
name (RFC 5987 `filename*` for a non-ASCII one), a media type fixed per extension
(`application/octet-stream` for unknown ones), `X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'; sandbox` and `Cache-Control:
no-store`. HTML or SVG a user or an agent stored therefore never renders as a page
of the app's origin. The request needs the bearer header like any other — the
app fetches the file and saves the body; a token never goes in the URL.
`404 not_found` when there is no such file.

### `DELETE /files/<path>`

`204`. Folders the deletion leaves empty are removed too. `404 not_found` when
there is no such file.

---

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
    { "id": 12, "order": 1, "stage": 1, "title": "Summary", "role": "Summariser", "allowed_tools": [], "is_output": false, "expected_output": "Five bullet points", "prompt": "Summarise:\n{article}", "model": "deepseek/deepseek-v4-flash", "condition": null, "review": null },
    { "id": 13, "order": 2, "stage": 2, "title": "Translated summary", "role": "Translator", "allowed_tools": null, "is_output": true, "expected_output": "The bullets, translated", "prompt": "Translate to {language}:\n{input}", "model": "openai/gpt-oss-120b", "condition": null, "review": null }
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
no longer available when the step runs, the run stops with `502
tool_unavailable` naming it — for example a tool of an integration that cannot
be reached. A step that does not select such a tool runs without it.
The native pipeline tools are scoped to the signed-in user; MCP servers come
from `MCP_SERVERS` and from the user's enabled integrations. When a built-in tool fails during a step (for example
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
`input` (`{input}` is each stage's input) or `feedback` (`{feedback}` is a
reviewer's feedback, see [review loops](#conditions-and-review-loops)). Any step, **in any stage**, inserts
a value with `{name}`, so later stages still see the original request. With
`inputs: []` the pipeline runs on one free-text input, as pipelines saved
before named inputs existed do.

### Conditions and review loops

Two more optional step fields change how work flows. Both are `null` by default
(and for every step saved before they existed), which is the plain behaviour
above.

**`condition`: "run this step only if…"**

```json
{ "source": "previous_output", "operator": "contains", "value": "blog" }
```

`source` is what the condition looks at: `previous_output` (what the previous
stage handed on, the step's `{input}`; in the first stage, the run's text),
`input:<name>` (one of the pipeline's named inputs) or `step:<order>` (the output
of a step in an **earlier** stage). `operator` is one of:

| Operator | Holds when the text… |
|---|---|
| `contains` / `not_contains` | contains / does not contain `value` |
| `equals` / `not_equals` | is / is not exactly `value` |
| `is_empty` / `not_empty` | is empty / is not empty (`value` is ignored and stored as `""`) |

Both sides are trimmed and compared ignoring case. `value` has at most 200
characters and is required by the operators that compare. The condition is read
right before the step would start. When it does not hold the step is
**skipped**: its status is `skipped`, its output empty, and it never counts as an
output. A skipped step is final, so a [resumed](#post-runsidresume) run keeps it
without judging the condition again. A stage's merged output leaves skipped steps
out (one step left passes its output on unchanged), and a stage in which every
step was skipped hands its input on as it received it.

**`review`: "send back for fixes"**

```json
{ "send_back_to_stage": 2, "max_rounds": 2 }
```

The step is a normal agent step whose prompt judges the work it receives. AIMIx
adds one rule to its system prompt: end the answer with a line `VERDICT: PASS`
or `VERDICT: REVISE`. When the reviewer's stage has finished, the engine reads
the **last** line of its output that holds only such a verdict (any case; it may
be wrapped in Markdown emphasis, a quote mark, a heading mark or a list dash, and
end in a full stop; a line with other words on it is not a verdict) and takes
that line out of the stored output. `REVISE` with rounds left sends the work
back: the stages from `send_back_to_stage` up to the reviewer's own run again, in
order, at most `max_rounds` (1 to 5) times, so they run at most `1 + max_rounds`
times in all. The steps of the stage it goes back to receive their usual prompt
plus a block "Feedback from the reviewer (round 2 of 3): …" holding the
reviewer's answer without the verdict line, unless their prompt places that
text itself with `{feedback}`. `PASS`, no verdict at all, or no rounds left
carry on to the next stage; running out of rounds on `REVISE` is not an error.

`{feedback}` is reserved like `{input}`: it is the reviewer's feedback while a
step is redone and empty otherwise, and no input may be named `feedback` (a
pipeline that declared one before keeps working: its own value wins). The stage
after a reviewer receives the reviewer's answer, not the work it judged, so ask
the reviewer to repeat the approved work when a later stage needs it, and mark
the step whose work is reviewed as the output rather than the reviewer.

**What a run records.** A step that runs again updates its own row in place: its
status goes back to `running`, its output is replaced when it finishes, and its
usage keeps adding up. `rounds` is the round the row is in (see
[Runs](#runs)) and a reviewer's row keeps its `verdict`. A spending limit and
approval gates work inside rounds like anywhere else.

**Rules, checked when a pipeline is saved** (`POST`, `PUT` and `PATCH`; a
`PATCH` checks what it leaves together with what it keeps) and again when a run
starts. A problem is a `400 validation_error` whose `detail` names the step in
plain words, for example `Step 3 (Publish): its condition looks at step 5, which
does not run before it (pick a step in an earlier stage).` Every problem is
listed.

- The `operator` is one of the six, the `source` one of the three kinds, and
  `value` is at most 200 characters and present where it is needed.
- An `input:<name>` source names a declared input; a `step:<order>` source names
  a step in a **strictly earlier** stage.
- `send_back_to_stage` is a stage that has steps and is **before** the
  reviewer's own; `max_rounds` is 1 to 5.
- **Review loops may not overlap.** A loop covers the stages from its target to
  its reviewer; two loops that share a stage (nested, interleaved, or two
  reviewers in one stage) are refused, so every step has one round counter and
  `1 + max_rounds` bounds how often it runs. Loops one after another are fine.

`POST /pipelines/generate` and `/revise` sanitise a planner's `condition` and
`review` by the same rules and drop (set to `null`) what cannot work instead of
failing the request.

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

Kept for API compatibility: it starts a run exactly like
[`POST /pipelines/<id>/runs`](#post-pipelinesidruns) — recorded in your run
history — and waits for its end. New clients start a run and poll it instead.

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

Either body may also carry `max_cost_usd` and/or `max_tokens`, the run's
[spending limits](#spending-limits). A run that reaches one ends the request
with `409 budget_exceeded`.

`200`:

```json
{
  "pipeline_name": "Summarise then translate",
  "final_output": "Résumé ...",
  "intermediate_results": [
    { "step_order": 1, "stage": 1, "title": "Summary", "model": "deepseek/deepseek-v4-flash", "input_used": "Long article text...", "output": "Summary ...", "is_output": false, "tool_calls": [], "skipped": false, "rounds": 1 },
    { "step_order": 2, "stage": 2, "title": "French summary", "model": "openai/gpt-oss-120b", "input_used": "Summary ...", "output": "Résumé ...", "is_output": true, "tool_calls": [{ "name": "list_pipelines", "status": "success" }], "skipped": false, "rounds": 1 }
  ]
}
```

`intermediate_results` holds every step's output, ordered by stage then `order`;
`is_output` is `true` on the results that are the pipeline's outputs (the marked
steps, or the last stage when none is marked), never on a step that was
`skipped` (its condition did not hold: `output` is `""`). `rounds` is above 1
for a step a [review loop](#conditions-and-review-loops) ran again; the result
is its newest round.
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
`502/503/504` agent or tool failures (the run stops and the response carries
no partial result; the recorded run keeps the steps that succeeded and can be
resumed), `409 conflict` if the run is stopped from the run history while
this request waits.

The call takes as long as its stages combined, and a parallel stage takes as
long as its slowest step. When a step's tool must [ask for approval](#approvals),
the call also waits until the run's owner answers (from the Runs page or the
[approval endpoints](#post-runsidapprovalsapproval_idapprove-and-decline)), or the
request expires after `APPROVAL_TIMEOUT_SECONDS`.

## Runs

A run is one execution of a pipeline. It executes in the background: start it,
then poll it. Every run is recorded until you delete it, together with the
pipeline as it was when the run started (`definition`), so editing or deleting
the pipeline later changes nothing about the run.

A run is `queued` (waiting for a free slot: at most `RUN_MAX_CONCURRENT` runs
execute at once), `running`, `waiting` (running, but a tool call waits for your
approval; see [Approvals](#approvals)), then `succeeded`, `failed`, `cancelled`
(you stopped it) or `interrupted` (the server stopped or restarted during the
run). `queued`, `running` and `waiting` are active. Each step is `pending`,
`running`, `succeeded`, `failed`, `cancelled` or `skipped` (its
[condition](#conditions-and-review-loops) did not hold, so it did not run); the
step that asked stays `running` while its run is `waiting`.

### `POST /pipelines/<id>/runs`

Same body as `POST /pipelines/<id>/run`. `202` → the run, `queued`, every step
`pending`. The inputs are checked first: a mismatch is a `400
validation_error` and nothing is saved; `404` for a pipeline that is not yours.
A failure of the model or a tool (or a missing API key) does not fail this
request: the run ends `failed` with that error.

The run object:

```json
{
  "id": 12,
  "pipeline_id": 7,
  "pipeline_name": "Summarise then translate",
  "trigger": "manual",
  "schedule_id": null,
  "status": "running",
  "error": null,
  "created_at": "2026-10-24T10:00:00Z",
  "started_at": "2026-10-24T10:00:01Z",
  "finished_at": null,
  "max_cost_usd": 0.5,
  "max_tokens": null,
  "usage": { "input_tokens": 1434, "output_tokens": 587, "cost_usd": 0.0127, "cost_complete": true },
  "input": "",
  "inputs": { "article": "Long article text...", "language": "French" },
  "final_output": "",
  "definition": {
    "name": "Summarise then translate",
    "inputs": [{ "name": "article", "label": "Article", "description": "" }, { "name": "language", "label": "Target language", "description": "" }],
    "steps": [{ "order": 1, "stage": 1, "title": "Summary", "role": "Summariser", "allowed_tools": [], "is_output": false, "expected_output": "Five bullet points", "prompt": "Summarise:\n{article}", "model": "deepseek/deepseek-v4-flash", "condition": null, "review": null }, "..."]
  },
  "steps": [
    { "step_order": 1, "stage": 1, "title": "Summary", "model": "deepseek/deepseek-v4-flash", "status": "succeeded", "input_used": "## Article\n\nLong article text...", "output": "Summary ...", "is_output": false, "tool_calls": [], "error": null, "started_at": "2026-10-24T10:00:01Z", "finished_at": "2026-10-24T10:00:09Z", "input_tokens": 1234, "output_tokens": 567, "cost_usd": 0.0123, "rounds": 1, "verdict": null },
    { "step_order": 2, "stage": 2, "title": "Translated summary", "model": "openai/gpt-oss-120b", "status": "running", "input_used": "Summary ...", "output": "", "is_output": true, "tool_calls": [], "error": null, "started_at": "2026-10-24T10:00:09Z", "finished_at": null, "input_tokens": 200, "output_tokens": 20, "cost_usd": 0.0004, "rounds": 1, "verdict": null }
  ],
  "pending_approvals": []
}
```

`pending_approvals` lists the tool calls the run waits on, oldest first (empty
unless the run is `waiting`); see [Approvals](#approvals).

`trigger` says what started the run: `manual` (you, from the app or the API),
`schedule` (one of your [schedules](#schedules); `schedule_id` names it, and
becomes `null` once the schedule is deleted while `trigger` stays) or `chat`
(the chat agent's `run_pipeline` tool). Runs recorded before schedules existed
read as `manual`.

`rounds` and `verdict` describe a [review loop](#conditions-and-review-loops).
`rounds` is the round the step's row is in: 1, or more when a loop sent the work
back and the step ran again (the row holds its newest round, so while a loop is
redone the steps still to run again show the round before). `verdict` is what a
reviewer's last answer decided, `"pass"` or `"revise"`, and `null` for any other
step, for a reviewer that gave none, and while a reviewer is running again. A
reviewer that ran out of rounds has `verdict: "revise"` and `rounds` of
`1 + max_rounds`. A skipped step has `started_at: null`; `definition` carries each
step's `condition` and `review` (`null` for a run saved before they existed).

`input` / `inputs` are what the run was started with. A step's `output` and
`tool_calls` appear as soon as it succeeds; `final_output` once the run
succeeds. `error` (on the run, and on the step that failed) is `null` or
`{"code", "detail"}` with the same codes as error responses, e.g.
`provider_timeout`. `pipeline_id` becomes `null` if the pipeline is deleted.
Timestamps are UTC; `duration = finished_at - started_at` of the latest attempt.

**Usage and cost.** Each step carries what its model calls used: `input_tokens`,
`output_tokens` and `cost_usd` (USD). They grow with every model call the step's
agent makes, so a running step shows its spend so far, and a step that failed or
was stopped keeps what it spent. Resuming never resets them: a step the run does
again adds its new calls to the earlier ones. The run's `usage` is computed from
its steps, over every attempt, as
`{"input_tokens", "output_tokens", "cost_usd", "cost_complete"}`:

- `cost_usd` is the known costs added up, in USD, and `null` when none is
  known (a model whose price is not known; its tokens are still counted).
- `cost_complete` is `false` when some tokens came from a model with no known
  cost, so `cost_usd` is then a floor. A run that has used nothing is complete,
  with `cost_usd: null`.

Where a call's cost comes from, best first: what the provider reports it
charged (OpenRouter returns `usage.cost` with every answer), else the model's
published prices in the catalogue (`llm/catalog.py`), else unknown. See
[LLM providers](llm-providers.md#usage-and-cost).

#### Spending limits

A run may carry `max_cost_usd` (a number above zero, in USD) and/or
`max_tokens` (a whole number of at least 1, counting tokens in and out), both
`null` for no limit. Send them in the body of `POST /pipelines/<id>/runs`; a
limit left out takes the server default, `RUN_DEFAULT_MAX_COST_USD` for the cost
(no limit when it is empty). A value that is not a positive finite number is a
`400 validation_error` and nothing is saved.

The limit is enforced while the run executes, not after: every finished model
call is added to the run's running total, which parallel steps share, and a
call is refused once the total has reached a limit. The run then stops as
`failed` with the error code `budget_exceeded`, and the step that was refused
fails with it:

```json
{ "error": { "code": "budget_exceeded", "detail": "This run stopped at $0.52 because it reached its $0.50 limit." } }
```

Steps that had finished keep their outputs. A call already in flight when the
limit is reached still finishes and is counted, so the total can pass the limit
by the calls then in flight (at most one per parallel step). A call that is cut
off in flight (a parallel step stopped by the failure of another) reports no
usage, so what the provider may still charge for it is not counted. A cost limit
cannot stop calls whose cost is unknown; use `max_tokens` for those.

### `GET /runs`

Your runs, newest first, one page at a time: `?limit=20&offset=0`, optionally
`&pipeline_id=7` for one pipeline's runs and `&status=waiting` for the runs in
one status. `limit` is 1–100 (default 20) and `offset` ≥ 0; an unknown `status`
or anything else out of range is a `400`. `?status=waiting&limit=1` is the cheap
way to know whether anything waits for you: read `total`. `200`:

```json
{ "items": [{ "id": 12, "pipeline_id": 7, "pipeline_name": "Summarise then translate", "trigger": "schedule", "schedule_id": 4, "status": "succeeded", "error": null, "created_at": "...", "started_at": "...", "finished_at": "...", "max_cost_usd": null, "max_tokens": null, "usage": { "input_tokens": 1434, "output_tokens": 587, "cost_usd": 0.0127, "cost_complete": true } }], "total": 42 }
```

Summaries carry no inputs, outputs, definition or steps; they do carry the run's
limits and its `usage` total, so a history can show what each run cost.

### `GET /runs/<id>`

The whole run. Poll it while it is `queued`, `running` or `waiting` (the app
polls every 1.5 seconds). `404` if it is missing or not yours.

### `POST /runs/<id>/cancel`

Stops a queued, running or waiting run at once: it becomes `cancelled`, a
running step `cancelled` (its model call is cut off), pending steps stay
`pending`, and the approvals still pending expire. A finished run comes back
unchanged, so calling it twice is safe. `200` → the run.

### `POST /runs/<id>/resume`

Continues a `failed`, `cancelled` or `interrupted` run from its first stage
that did not fully succeed, with your current model settings: the steps that
succeeded (or were skipped) keep their outputs and do not run again, the others
go back to `pending`, and the run executes its own `definition`. Any other run
comes back unchanged. `200` → the run, `queued` again.

A run stopped inside a [review loop](#conditions-and-review-loops) picks the loop
up where it was, from what the rows hold. The newest `rounds` of any step in a
loop's stages is the round it was in (one time fewer than that, the work had been
sent back). Only a result saved in that round is kept; one from an earlier round
is redone, and a reviewer's saved `REVISE` answer is read back as the feedback of
the round that followed it while the reviewer has not run again. So a run stopped
while the work was being redone redoes that stage with the reviewer's feedback; a
run stopped between two rounds sends the work back when it resumes; a loop whose
rounds were used up, or that ended on `PASS`, is not run again. The one thing a
resume can lose is the feedback for a step that had not yet run in a round whose
reviewer had already run again (the reviewer's earlier answer is gone by then).

The body is optional: `{"max_cost_usd": 2.0}` and/or `{"max_tokens": 50000}` set
new [spending limits](#spending-limits); a limit left out stays as the run has
it. The limits cover the whole run, every attempt together, so a run that
stopped at its limit needs a higher one: resuming it under a limit it has
already reached is a `409 budget_exceeded` (`"This run already reached its $0.50
limit (it used $0.52). Raise the limit to resume it."`) and the run stays as it
was. An invalid limit is a `400 validation_error`.

### `DELETE /runs/<id>`

`204`. Only a finished run can be deleted: a queued, running or waiting one is a
`409 conflict` — stop it first.

## Approvals

An agent's tool call can change something outside AIMIx (send an email, update a
CRM). Inside a run, a tool that **asks first** is held at a gate until you
approve or decline it:

- every tool of an operator `MCP_SERVERS` entry, unless the operator set
  `MCP_REQUIRE_APPROVAL=false`;
- every tool of one of your [integrations](#integrations) whose
  `require_approval` is `true` (the default);
- any tool named in the operator's `AGENT_APPROVAL_TOOLS` (built-in tools; none
  by default).

While a request waits the run is `waiting` and `pending_approvals` lists it. The
chat has no run to pause, so these tools are not offered to the chat agent; it
can still start a pipeline run, whose steps ask. An approved call runs. A
declined one does not run, and the agent receives an error result ("The user
declined this action…") it can react to; the run goes on. A request nobody
answers within `APPROVAL_TIMEOUT_SECONDS` (1800 by default) *expires* and counts
as declined; so does a request of a run that is stopped, fails, or is cut by a
restart (a resumed run asks again).

A request, as listed in `pending_approvals`:

```json
{ "id": 31, "step_order": 2, "tool_name": "crm_send_email", "tool_source": "crm",
  "tool_description": "Send an email to a contact.",
  "arguments": { "to": "ada@example.com", "subject": "Launch" },
  "arguments_truncated": false, "status": "pending",
  "created_at": "2026-10-24T10:00:12Z", "expires_at": "2026-10-24T10:30:12Z" }
```

`tool_source` is an integration's name, `MCP` (the operator's servers) or `AIMIx`
(built-in tools). `arguments` are what the agent passed, as JSON, so you can see
what would happen; a long text value is shortened to keep the whole within
`APPROVAL_ARGUMENTS_MAX_CHARS` (4000), and `arguments_truncated` says so (the tool
itself gets the full text). Arguments are never written to the server's logs.

### `POST /runs/<id>/approvals/<approval_id>/approve` and `/decline`

No body. `200` → the run, as `GET /runs/<id>` returns it (`running` again once
nothing else waits). Answering is idempotent: the same answer twice changes
nothing. Failures:

| Status | `error` | When |
|---|---|---|
| 404 | `not_found` | Not your run, or no such request in it |
| 409 | `conflict` | The request already got the other answer, or it expired (time is up, or the run stopped); `detail` says which |

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
      { "order": 1, "stage": 1, "title": "Pros", "role": "Analyst", "allowed_tools": [], "is_output": false, "expected_output": "A bullet list of pros", "prompt": "List the pros in: {review}", "model": "deepseek/deepseek-v4-flash", "condition": null, "review": null },
      { "order": 2, "stage": 1, "title": "Cons", "role": "Analyst", "allowed_tools": [], "is_output": false, "expected_output": "A bullet list of cons", "prompt": "List the cons in: {review}", "model": "deepseek/deepseek-v4-flash", "condition": null, "review": null },
      { "order": 3, "stage": 2, "title": "Reply", "role": "Writer", "allowed_tools": [], "is_output": true, "expected_output": "A polite reply under 120 words", "prompt": "Reply to {review} using: {input}", "model": "deepseek/deepseek-v4-flash", "condition": null, "review": null }
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
The planner may also give a step a [`condition` or a `review`](#conditions-and-review-loops)
("only run the SEO step if the topic mentions blogs", "add a QA agent that sends
the draft back to the writer up to 2 times"). They are read forgivingly (numbers
written as text are accepted; the `value` of `is_empty` and `not_empty` is
dropped) and then checked together with the plan: one that is malformed, or
cannot work in this plan (an unknown operator or source, an input the plan does
not declare, a step that is not in an earlier stage, a stage that is not earlier
or has no steps, rounds outside 1 to 5, a loop that shares a stage with another)
becomes `null` and the rest of the plan is kept; of two loops that share a stage,
the one that starts later is dropped. Steps are numbered by position, so
`step:2` means the second step in the list.
If the planner's answer has no usable JSON: `502 upstream_response_invalid`.

### `POST /pipelines/revise`

Changes a pipeline from one sentence. The body holds the current draft, saved or
not, and what to change:

```json
{ "pipeline": { "name": "Launch kit", "inputs": [ ... ], "steps": [ ... ] },
  "instruction": "Add an SEO agent that works alongside the marketing agent",
  "planner_model": "openai/gpt-oss-120b" }
```

`pipeline` has the fields of a pipeline you save (`name`, `inputs`, `steps`; ids
are ignored) and is checked the same way, except that its name and step prompts
may be blank: an unfinished draft can be revised, and the planner writes the
missing prompts. `instruction` is required, non-blank and at most 2,000
characters (`REVISION_INSTRUCTION_MAX_LENGTH`). `planner_model` is optional
(defaults to your default model). `200`:

```json
{
  "revised_pipeline": { "name": "Launch kit", "inputs": [ ... ], "steps": [ ... ] },
  "changes": [
    { "target": "step", "kind": "added", "label": "SEO keywords", "order": 3, "fields": [] },
    { "target": "step", "kind": "changed", "label": "Research", "order": 1, "fields": ["prompt", "allowed_tools"] }
  ],
  "available_models": ["deepseek/deepseek-v4-flash", "..."]
}
```

Nothing is saved: review the revision, then save it with `POST /pipelines/` or
`PUT /pipelines/<id>/`. `revised_pipeline` is the whole pipeline, unchanged
steps included. The planner gets the same tool catalogue and models as for
`POST /pipelines/generate`, and its answer is cleaned up the same way (see
above); when it gives no name, the draft's name is kept.

`changes` lists every difference: a rename first, then inputs, then steps, each
in the revision's order with removals last.

| Field | Meaning |
|---|---|
| `target` | `pipeline` (a rename), `input` or `step` |
| `kind` | `added`, `removed` or `changed` |
| `label` | The new name, the input's name, or the step's title (`Step N` without one) |
| `order` | A step's order in the revision (in the draft for a removed step); `null` otherwise |
| `fields` | For `changed`, what differs, in this order: `title`, `role`, `prompt`, `expected_output`, `model`, `allowed_tools`, `stage`, `is_output`, `condition`, `review` for a step; `label`, `description` for an input; `name` for the pipeline |

Steps are paired before they are compared: an unchanged step first, then the
same title (ignoring case and spacing), then the same prompt, then the same
position. Inputs are paired by name, so a renamed input reads as one removed and
one added. Text is compared without surrounding whitespace, tool lists in any
order, and a step's `condition` and `review` as a whole (any difference in one is
one changed field). `stage` is listed only when a step now runs at another point:
renumbered stages, a stage added or removed with its own steps, or a step only
shifted by another step's move do not count. A draft may carry conditions and
review loops that do not work yet (the builder can hold a half-finished flow):
only a save checks them, and the planner's answer is cleaned up as for generate.

Errors: `400 validation_error`, before the planner is asked, for a blank or too
long instruction or a draft that could not be saved for another reason (no
steps, a repeated `order`, an unknown model, an invalid input name);
`502 upstream_response_invalid` when the planner's answer holds no usable
pipeline; `502/503/504` for provider failures, as for generate.

---

## Usage

### `GET /usage`

What your own runs used and cost lately, in all and per pipeline. `?days=30`
(1–366, default 30) counts the runs created in that many days back from now;
anything else is a `400 validation_error`. Only your runs are ever counted.
`200`:

```json
{
  "days": 30,
  "since": "2026-09-24T10:00:00Z",
  "runs": 12,
  "usage": { "input_tokens": 100000, "output_tokens": 23456, "cost_usd": 1.234, "cost_complete": true },
  "pipelines": [
    { "pipeline_id": 7, "pipeline_name": "Summarise then translate", "runs": 8, "usage": { "input_tokens": 90000, "output_tokens": 20000, "cost_usd": 1.2, "cost_complete": true } },
    { "pipeline_id": null, "pipeline_name": "Old idea", "runs": 1, "usage": { "input_tokens": 10000, "output_tokens": 3456, "cost_usd": 0.034, "cost_complete": true } }
  ]
}
```

`usage` has the shape of a run's [`usage`](#post-pipelinesidruns). `pipelines`
lists the costliest first. The runs of a pipeline that was deleted stay in the
report under the name they had, with `pipeline_id: null` (deleted pipelines of
the same name are listed together). Chat messages are not counted: only pipeline
runs.

---

## Schedules

A schedule starts runs of one of your pipelines on its own, at a preset
frequency, with the run inputs filled in once. It runs the pipeline **as last
saved**, with your LLM provider and key (the Settings page, else the server's),
and each run it starts is an ordinary [run](#runs) marked `trigger: "schedule"`.
Schedules are checked every `SCHEDULER_TICK_SECONDS` (30), so a run starts at
most that long after its time. A schedule that was overdue (the server was down)
runs **once** when the server is back, not once per missed time.

A schedule object:

```json
{
  "id": 4,
  "pipeline_id": 3,
  "pipeline_name": "Competitor news",
  "pipeline_inputs": [{ "name": "topic", "label": "Topic", "description": "" }],
  "frequency": "weekly",
  "time": "09:00",
  "weekday": 0,
  "day_of_month": null,
  "timezone": "Europe/Paris",
  "input": "",
  "inputs": { "topic": "competitors" },
  "enabled": true,
  "next_run_at": "2026-10-26T08:00:00Z",
  "last_run": { "id": 12, "status": "succeeded", "created_at": "2026-10-19T08:00:00Z" },
  "last_error": null,
  "created_at": "2026-10-24T10:00:00Z"
}
```

| Field | Meaning |
|---|---|
| `frequency` | `hourly` (the shortest), `daily`, `weekdays` (Monday to Friday), `weekly` or `monthly` |
| `time` | `"HH:MM"` on a 24-hour clock, in `timezone`. An `hourly` schedule uses the minutes only (its hour reads `00`) |
| `weekday` | 0 (Monday) to 6 (Sunday); required for `weekly`, `null` for the others |
| `day_of_month` | 1 to 31; required for `monthly`, `null` for the others. A month that is too short for it uses its last day (the 31st runs on 30 April and 28 February) |
| `timezone` | An IANA name the server knows, such as `Europe/Paris`, `America/New_York` or `UTC` |
| `input` / `inputs` | What each run is given, with the rules of [`POST /pipelines/<id>/runs`](#post-pipelinesidruns): free text for a pipeline without named inputs, a value for each named input otherwise. `pipeline_inputs` lists the pipeline's inputs |
| `enabled` | Whether it runs. Off, it keeps its settings and `next_run_at` is `null` |
| `next_run_at` | The next time it starts, in UTC |
| `last_run` | The newest run it started (by itself or by [run now](#post-schedulesidrun)); `null` before the first, or when those runs were deleted |
| `last_error` | Why its latest time could not start a run (for example no API key); `null` when it started. The schedule has already moved to its next time. An edit that changes what it runs or when, or turns it on, clears it (it has not failed yet); turning it off keeps it |

A time is read on the zone's wall clock, so `09:00` stays 09:00 across
daylight-saving changes. When the clocks go forward, a time in the skipped hour
runs as much later as they jumped (02:30 becomes 03:30); when they go back, a
time that happens twice runs once, the first time. An `hourly` schedule follows
real hours: it runs both times through a repeated hour, and not in a skipped one.

### `GET /schedules`

Your schedules, oldest first. `?pipeline_id=3` narrows them to one pipeline's
(another account's pipeline gives an empty list).

### `POST /schedules`

```json
{ "pipeline_id": 3, "frequency": "weekly", "time": "09:00", "weekday": 0,
  "timezone": "Europe/Paris", "inputs": { "topic": "competitors" }, "enabled": true }
```

`201` → the schedule, with its `next_run_at`. Send `input` (free text) or
`inputs` (named values) as for a run; `enabled` defaults to `true`. Fields the
frequency does not use are ignored and stored as `null`. The same checks as
starting a run apply **before anything is saved**:

| Status | `error` | When |
|---|---|---|
| 400 | `validation_error` | An unknown `timezone`; a `time` that is not `HH:MM`; a weekly schedule without `weekday` or a monthly one without `day_of_month`; inputs the pipeline does not take (blank text, a missing or unknown named input, text sent to a pipeline with named inputs); a pipeline without steps; or `SCHEDULES_MAX_PER_USER` (20) schedules already |
| 404 | `not_found` | The pipeline is missing or not yours |

### `PATCH /schedules/<id>`

```json
{ "time": "18:30", "enabled": true }
```

Every field is optional and one left out keeps its value; sending the same body
twice leaves the same state. Timing fields change one by one. `input` and
`inputs` replace what each run is given **as a whole** (the one left out becomes
empty). The next time is worked out again when the timing changes or the schedule
is turned on; changing only the inputs keeps it, so a time that is due is not
postponed by an edit. Turning a schedule **off** always works and clears
`next_run_at`. Turning it on, or changing its inputs, checks them again against
the pipeline (`400` if they no longer fit). `200` → the schedule.

### `DELETE /schedules/<id>`

`204`. The runs it started stay in the history, with `schedule_id` `null`.
Deleting a pipeline deletes its schedules too.

### `POST /schedules/<id>/run`

Starts one of the schedule's runs now, with its saved inputs, even when the
schedule is off. `202` → the run (`trigger: "schedule"`, `queued`), to follow with
`GET /runs/<id>`; the schedule's timing does not change. A pipeline that no longer
takes the saved inputs is a `400`, and nothing is saved.

### `POST /schedules/preview`

```json
{ "frequency": "monthly", "time": "09:00", "day_of_month": 31, "timezone": "Europe/Paris" }
```

`200` → `{ "next_run_at": "2026-10-31T08:00:00Z" }`: when a schedule with that
timing would first run, worked out by the same rule the scheduler uses.
Nothing is saved. The app calls it to show "next run" while the form is filled
in. The same `400`s as saving apply to the timing.

Every schedule route answers `404` for another account's schedule.

---

## Templates

Ready-made missions a user can start from. The catalogue is code
(`api/services/templates/`), the same for every account; nothing is stored
until a template is used, and then only the caller's own pipeline.

### `GET /templates`

`200` → every template, in gallery order:

```json
[
  {
    "slug": "market-research-brief",
    "title": "Market research brief",
    "category": "Research",
    "description": "Size up a market: its size, customers, trends and risks, in a brief you can act on.",
    "inputs": [
      { "name": "market", "label": "Market", "description": "The market or product category to research, ..." },
      { "name": "goal", "label": "Your goal", "description": "What the brief should help you decide, ..." }
    ],
    "step_count": 5,
    "stage_count": 3
  }
]
```

`category` is `Research`, `Documents`, `Data` or `Marketing`. `inputs` are the
named run inputs the pipeline will declare, and `step_count` is its number of
agents. The steps themselves are only returned once the template is used.

| Slug | Agents · stages | The user provides |
|---|---|---|
| `market-research-brief` | 5 · 3 | `market`, `goal` |
| `competitor-analysis` | 4 · 3 | `product`, `competitors` |
| `document-digest` | 5 · 3 | `document`, `reader` |
| `meeting-actions` | 4 · 3 | `notes`, `meeting` |
| `data-insights-report` | 4 · 3 | `data`, `question` |
| `seo-content-brief` | 4 · 3 | `topic`, `audience` |
| `content-calendar` | 4 · 3 | `topic`, `audience`, `channels` |
| `product-launch-plan` | 5 · 3 | `product`, `goal`, `launch` |

Every template runs independent work in parallel in its first stage, then a
writer, and ends with a single reviewer step, the only `is_output` step: it
checks the draft against the run's inputs (and, for `document-digest` and
`meeting-actions`, against the original text) and returns the corrected final
version. A document or a CSV file can be attached to the run input as usual
(`POST /documents/extract`); `data-insights-report` can also open a CSV file
from the workspace by name.

### `POST /templates/<slug>/use`

Creates the caller's own pipeline from the template. The body is optional:

```json
{ "name": "Plant snacks brief" }
```

`name` (non-blank, at most 255 characters) defaults to the template's `title`.
`201` → the created pipeline, in the same shape as `GET /pipelines/<id>/`, with
the template's inputs and its steps in order (`order` 1..N). Templates never
name a model or a tool the caller lacks:

- each step's `model` is the caller's default model (Settings page, else
  `.env`);
- each step's `allowed_tools` keeps, in the template's order, only the tools
  `GET /agent-tools` currently lists for the caller, which may leave `[]`.
  Templates name built-in tools only (`web_search`, `fetch_url`, `calculator`,
  `current_datetime`, `list_workspace_files`, `read_csv`). For example,
  `web_search` is dropped without `TAVILY_API_KEY`, and both web tools while
  workspace readers suppress them (see [Agent tools](#agent-tools)); the
  prompts then work from what the model knows and label unverified figures.

This is the rule the planner's output goes through
(`services/pipelines.sanitise_step`). Using a template twice creates two
pipelines.

| Status | `error` | When |
|---|---|---|
| 400 | `validation_error` | `name` is blank or too long |
| 404 | `not_found` | No template has that slug (checked before any tool discovery) |
| 502 | `tool_unavailable` | A configured MCP server could not be reached while listing the caller's tools |
| 503 | `provider_not_configured` | The caller's saved key can no longer be decrypted (as for `GET /models`) |

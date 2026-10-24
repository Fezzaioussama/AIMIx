# Known issues and technical debt

Each entry says where the issue is, what goes wrong, and a suggested fix.
Delete an entry when you fix it.

## Gaps

### 1. Pipeline runs block the request

`POST /pipelines/<id>/run` waits for the multiagent graph to finish inside the
request. Agent steps run asynchronously within a stage, but a long pipeline
can still hold the request for minutes (up to stages × `AGENT_TIMEOUT_SECONDS`).
This conflicts with AGENTS.md §6 ("no long-running work in the request path").
The frontend waits up to one hour, but `AGENT_TIMEOUT_SECONDS` bounds each step,
so a run with several slow stages can still time out on the client while the
server keeps going.

**Fix options:** stream step results as they complete (like chat), or run the
pipeline as a background job and let the client poll a run resource.

### 3. The pipeline list is not paginated

`GET /api/pipelines/` returns all of the user's pipelines. This is fine for now;
add `limit`/`offset` query parameters in the repository and endpoint (and update
the client) if lists grow large.

### 4. Pipeline runs have no durable state or approval flow

The synchronous run response includes step outputs and tool names/statuses,
but no run record or LangGraph checkpoint is saved. A failed or interrupted run
cannot be inspected or resumed. Tool actions execute without an approval step.

**Fix:** persist run and step state, expose run status, and introduce an
explicit approval gate for actions that require review.

### 5. Document inputs are read in the request thread

`POST /documents/extract` parses, renders and OCRs in the request's worker
thread. Each step is bounded (size, page, row, pixel and character limits, and
`DOCUMENT_OCR_TIMEOUT_SECONDS` per OCR'd page), but the request as a whole has
no wall-clock timeout: a long scan holds a worker for minutes, at worst
`DOCUMENT_OCR_MAX_PAGES` x `DOCUMENT_OCR_TIMEOUT_SECONDS` in OCR alone, which
conflicts with AGENTS.md §6 ("no long-running work in the request path"). PDFium
rendering is serialised across the process (it is not thread-safe) and has no
time limit of its own, so one slow page to render (heavy vector art) delays every
other scan being rendered. The request-size guard can only see a declared
`Content-Length`: a chunked upload is still capped, but only after the framework
has spooled it.

Not read at all: legacy binary Office files (`.doc`, `.xls`, `.ppt`), `.xlsm`,
SmartArt and chart text in slides, handwriting beyond what Tesseract manages,
and scanned pages whose text layer holds only a little text (a page number, say),
which are not sent to OCR.

**Fix:** run extraction as a background job in worker processes (a process per
render also lifts the PDFium lock) with a wall-clock timeout and let the client
poll, and cap request bodies at the reverse proxy as well.

### 6. Integrations: what the first version leaves out

Users' own MCP servers (`api/services/integrations/`) work with static headers
only. Their URLs are stored as entered, so a service that puts its token in the
URL keeps it unencrypted at rest (header values are encrypted). A tool call
that fails at the connection level stops the run, as for `MCP_SERVERS`, instead
of reaching the agent as an error result. "Test connection" results live only
in the open page, and the test endpoint has no rate limit beyond its timeout.
The address check leaves the DNS-rebinding window described in
[deployment.md](deployment.md#users-integrations-their-own-mcp-servers).

**Fix options:** encrypt the URL and show only its host; support the MCP OAuth
flow; a tool interceptor that turns a failed call into an error result; store
the last test's time and tool count; rate-limit tests like auth requests; pin
connections to the checked address in a custom httpx transport.

`POST /files` has the same request-size guard and the same chunked-upload caveat,
and an agent reading a PDF or Word file from its workspace runs the same readers
in the agent's thread.

### 6. Files: no pagination, and a narrow quota race on replacement

`GET /api/files` returns every file a user has; only `WORKSPACE_MAX_TOTAL_BYTES`
bounds the list. The quota is checked before a write and, for a new file, again
once its bytes are on disk, so concurrent new files never stay over the limit.
A replacement (`replace=true`) is checked only before it lands, so two
simultaneous replacements by one user can overshoot by the growth of one file.
A replacement is staged as a hidden `.upload-*.part` file; one left by a crash
is invisible to the user and to the quota, and nothing removes it.

**Fix:** add `limit`/`offset` to the listing; take a per-user lock (database row
or `flock`) around a replacement; sweep stale `.part` files on startup.

### 7. PDF artifacts: italics, CJK and right-to-left text

The image's `fonts-dejavu-core` has no italic face, so italics in a PDF print
upright (Word files keep them). DejaVu Sans covers Latin, Greek, Cyrillic and
more, but not Chinese, Japanese or Korean, which print as boxes; Arabic and
Hebrew print unshaped and left to right. A deployment without the font falls
back to Helvetica: Western European text only.

**Fix:** point `PDF_FONT_PATH` / `PDF_BOLD_FONT_PATH` at a family that covers the
scripts you need (for example Noto), add an italic font setting, and enable
ReportLab's optional shaping extras for right-to-left text.


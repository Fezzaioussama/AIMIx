# Known issues and technical debt

Each entry says where the issue is, what goes wrong, and a suggested fix.
Delete an entry when you fix it.

## Gaps

### 3. The pipeline list is not paginated

`GET /api/pipelines/` returns all of the user's pipelines. This is fine for now;
add `limit`/`offset` query parameters in the repository and endpoint (and update
the client) if lists grow large.

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

### 8. Approval gates: what they leave out

Tools of MCP servers and integrations (and the built-in tools in
`AGENT_APPROVAL_TOOLS`) wait for the run owner's OK inside a pipeline run
([architecture.md](architecture.md#approval-gates)). Limits of the first version:

- **Chat cannot ask.** The tools that ask first are not offered to the chat agent,
  so with the defaults (`MCP_REQUIRE_APPROVAL=true`, integrations asking) chat has
  no MCP tools until the operator or the user switches approval off.
- **Every call asks, or none does.** There is no "always allow this tool" or
  "allow for this run"; the choice is per source (the operator's servers, one
  integration) and a step that makes ten calls asks ten times.
- **Built-in tools do not ask by default.** `web_search`, `fetch_url`,
  `save_artifact`, `run_python` and the workspace tools act unattended unless
  `AGENT_APPROVAL_TOOLS` names them.
- **A step cannot be approved ahead of time**, and the builder does not mark
  which tools will ask. The wait counts toward the step's `AGENT_TIMEOUT_SECONDS`,
  and a restart expires the requests (a resumed run asks again).
- **Waiting is polled.** A run reads the database about once a second
  (`APPROVAL_POLL_SECONDS`) and the page polls the run every 1.5 s, so an answer
  takes up to a second or two to show. There is no notification outside the Runs
  tab's count, and no email or push.
- **The compatibility endpoint blocks.** `POST /pipelines/<id>/run` and chat's
  `run_pipeline` wait for a run's end, so one that asks keeps its caller waiting
  until the owner answers on the Runs page (or the request expires).

**Fix options:** per-tool "always allow" rules saved with the integration; a
`requires_approval` flag in `GET /agent-tools` so the builder can show which
tools will ask; pausing the step's timeout clock while it waits; push or email
notifications for waiting runs; letting chat ask inline.

### 6. Runs execute inside the API process

The run executor (`api/services/run_executor.py`) is an asyncio loop in the API
process, and its queue lives in memory. That is enough for the single
container this deploys as, but a second process (another replica or Uvicorn
worker) would not share the queue, and its start-up recovery would mark the
first process's active runs as interrupted. A restart interrupts the runs in
progress; they have to be resumed by hand. Run progress is polled (every 1.5 s
per open run), not pushed.

**Fix:** when more than one process is needed, move execution to a worker
behind a shared queue (the `RunExecutor` port is the seam), scope recovery to
the worker that owned a run, optionally resume interrupted runs
automatically, and push progress with server-sent events.

### 7. A run's spending limit is checked between model calls

A limit stops a run by refusing its *next* model call once the total has
reached it (`api/services/run_budget.py`); a call cannot be priced before it is
made. So:

- A call in flight when the limit is reached still finishes and is counted: a
  run can pass its limit by one call per parallel step, and a single call that
  costs more than the whole limit is not prevented.
- A call cut off in flight (a parallel step stopped because another failed, or
  a run stopped by its owner) reports no usage, so what the provider may charge
  for it is not counted.
- A cost limit cannot stop calls whose cost is unknown (a model with no known
  price). Only a token limit can, and the app offers a cost limit; a token limit
  is set through the API.
- A step's `cost_usd` adds up the calls whose cost is known. If a provider
  reports it on only some calls, the step shows a floor and nothing marks it
  incomplete: a run's `cost_complete` turns `false` only when a step used
  tokens and has no cost at all.
- Usage covers pipeline runs, not chat messages, and the chat agent's
  `run_pipeline` tool starts runs under the server default limit only.

**Fix:** refuse a call that cannot fit the remaining budget, from an estimate of
its prompt size and the model's maximum output (a pre-flight check in
`RunMeter.check`); keep a `cost_complete` column on `run_steps` so a partial
cost is visible; count chat usage through the same `UsageCallback` where
`services/agent.py` builds its model; give the chat tool an optional limit.


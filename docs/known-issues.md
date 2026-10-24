# Known issues and technical debt

Each entry says where the issue is, what goes wrong, and a suggested fix.
Delete an entry when you fix it.

## Gaps

### 2. No retry policy for provider calls

AGENTS.md §6 asks for an explicit retry policy. The direct provider adapter
(`llm/base.py`, planning) makes no retries. The agent models are another
matter: `llm/agent_models.py` builds `ChatOpenRouter` with `max_retries=0`,
which makes langchain-openrouter pass no retry config, so the `openrouter`
SDK's own default applies — it retries 5xx responses and connection errors
with exponential backoff for up to an hour. Pipeline steps and chat on
OpenRouter therefore retry server errors today (stopping a run still cuts
them off at once). Decide on a policy, then document "no retries" or add
bounded retries with backoff for transient errors (timeouts, 429, 5xx), and
pass an explicit `RetryConfig` to the OpenRouter client either way.

### 3. The pipeline list is not paginated

`GET /api/pipelines/` returns all of the user's pipelines. This is fine for now;
add `limit`/`offset` query parameters in the repository and endpoint (and update
the client) if lists grow large.

### 4. Tool actions have no approval flow

Runs are recorded step by step and can be stopped and resumed, but a step's
agent calls its tools (web fetch, workspace writes, MCP tools) without asking
anyone first.

**Fix:** an explicit approval gate for actions that require review: pause the
run before such a step (a new resumable status, see "Extension points" in
[architecture.md](architecture.md#extension-points)) and resume it once
approved.

### 5. Document inputs: no OCR, and uploads are read in the request thread

`POST /documents/extract` reads text only. A scanned PDF or an image has no
text layer, so it is refused with a message saying it needs OCR; image and
spreadsheet formats (`.png`, `.xlsx`, `.pptx`) are not supported at all.
Parsing runs in the request's worker thread with size, page and character
limits but no wall-clock timeout, and the request-size guard can only see a
declared `Content-Length`: a chunked upload is still capped, but only after the
framework has spooled it.

**Fix:** add an OCR reader (and image or spreadsheet readers) to the `READERS`
registry, run extraction in a worker with a timeout, and cap request bodies at
the reverse proxy as well.

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


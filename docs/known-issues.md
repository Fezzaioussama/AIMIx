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


# Known issues and technical debt

Found while documenting the code (2026-09-27). Each entry says where the issue
is, what goes wrong, and a suggested fix. Delete an entry when you fix it.

## Bugs

### 1. Saving an existing pipeline creates a duplicate

`frontend/src/core/api/pipelines.ts` → `savePipeline` always sends
`POST /api/pipelines/`, even when the pipeline already has an `id`
(`usePipelineBuilder.save`). Editing a saved pipeline and pressing **Save**
creates a second copy instead of updating it.

**Fix:** when `pipeline.id` is set, send `PUT` to `/api/pipelines/<id>/` (add a
path helper in `endpoints.ts`), and add a test.

### 2. Duplicate step `order` returns a 500

`PipelineStep` has a unique constraint on `(pipeline, order)`, but
`PipelineSerializer` never checks that orders are unique. A payload with two
steps at `order: 1` raises `IntegrityError` in `bulk_create` → HTTP 500 instead
of `400 validation_error`.

**Fix:** in `PipelineSerializer.validate_steps`, reject repeated `order` values;
add a serializer test.

## Gaps

### 3. No access-token refresh on the client

`API.refresh` is declared in `endpoints.ts` but never used. When the access
token expires (60 min by default), the next call gets a 401, the client clears
the tokens, and the user is sent back to `/login`, even though a valid refresh
token was stored.

**Fix:** in `core/api/client.ts`, on a 401 try one `POST /api/token/refresh`
with the stored refresh token, save the new access token, and retry the
original request once.

### 4. Pipeline runs block the request

`POST /pipelines/<id>/run` calls every step synchronously inside the request, so
a long pipeline holds a worker for minutes (up to stages × `LLM_TIMEOUT_SECONDS`).
This conflicts with AGENTS.md §6 ("no long-running work in the request path").
The frontend waits up to one hour, but `LLM_TIMEOUT_SECONDS` bounds each call,
so a run with several slow stages can still time out on the client while the
server keeps going.

**Fix options:** stream step results as they complete (like chat), or run the
pipeline as a background job and let the client poll a run resource.

### 5. No retry policy for provider calls

AGENTS.md §6 asks for an explicit retry policy. There are currently no retries,
which is safe but undocumented in code. Decide on a policy, then either document
"no retries" in `llm/base.py` or add bounded retries with backoff for transient
errors (timeouts, 429, 5xx).

### 6. The pipeline list is not paginated

`GET /api/pipelines/` returns all of the user's pipelines. This is fine for now;
add DRF pagination (and update the client) if lists grow large.

## Documentation drift

- The top-level `README.md` stack table says "TogetherAI via the Together Python
  SDK", but the default provider is **OpenRouter** through the `openai` SDK;
  both are supported.
- The README quick start does not include `make migrate`, which is needed on a
  fresh clone before the first login.

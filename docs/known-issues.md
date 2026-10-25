# Known issues and technical debt

Each entry says where the issue is, what goes wrong, and a suggested fix.
Delete an entry when you fix it.

## Gaps

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

### 8. Scheduled runs: what the first version leaves out

Schedules (`api/services/schedules/`) start runs from a thread inside the API
process, so they share every limit of entry 6 above: one process, nothing runs
while it is down. Beyond that:

- **At most once, not at least once.** The scheduler claims an occurrence (moves
  `next_run_at`) *before* it starts the run, so two processes never start the same
  one. A process that dies between the claim and the run being saved loses that
  one occurrence, with no trace on the schedule.
- **Missed times are not replayed.** After downtime an overdue schedule runs once,
  not once per missed time, and there is no "catch up" option. A run starts up to
  `SCHEDULER_TICK_SECONDS` (30 s) after its time.
- **Runs can overlap.** A schedule starts its next run even if the previous one is
  still queued or running (an hourly pipeline that takes two hours); only
  `RUN_MAX_CONCURRENT` bounds them, the rest wait queued.
- **Presets only.** Hourly, daily, weekdays, weekly (one weekday) and monthly (one
  day); hourly is the shortest. No cron expressions, "every 15 minutes", several
  weekdays, end dates or one-off "run at" times.
- **Failures are only shown, not acted on.** A time that could not start a run
  (no API key, inputs the pipeline no longer takes) is saved as the schedule's
  `last_error`, and the next time overwrites it. There is no history of such
  times, no notification, and no switching off after repeated failures; a
  scheduled run that starts and then fails is an ordinary failed run in History.
- **A schedule follows the pipeline, not the other way round.** It always runs the
  pipeline as last saved, so editing the pipeline's named inputs can make a
  schedule's saved inputs invalid; it finds out at its next time, not when the
  pipeline is saved.
- **No per-schedule history.** The list shows each schedule's last run only;
  `GET /api/runs` cannot be filtered by schedule, and History just marks the runs
  a schedule started.
- **Time zone names** come from the browser's `Intl` list in the form, while the
  server accepts any name its database knows; a zone the browser lacks is shown in
  UTC. Daylight-saving rules (a skipped hour runs later, a repeated hour runs once,
  hourly follows real hours) are documented in
  [architecture.md](architecture.md#scheduled-runs).

**Fix:** to lose no occurrence, record the claimed occurrence and create the run
in one transaction (or keep an `occurrences` table and start from it); add an
"only when the last run is finished" option and a `schedule_id` filter on
`GET /api/runs`; keep the last few start failures, notify the owner and pause a
schedule after repeated ones; check a pipeline's schedules when it is saved. Moving
execution to a worker (entry 6) also moves the scheduler there.


# Known issues and technical debt

Each entry says where the issue is, what goes wrong, and a suggested fix.
Delete an entry when you fix it.

## Gaps

### 1. The pipeline list is not paginated

`GET /api/pipelines/` returns all of the user's pipelines. This is fine for now;
add `limit`/`offset` query parameters in the repository and endpoint (and update
the client) if lists grow large.

### 2. Document inputs are read in the request thread

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

### 3. Integrations: what the first version leaves out

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

### 4. Files: no pagination, and a narrow quota race on replacement

`GET /api/files` returns every file a user has; only `WORKSPACE_MAX_TOTAL_BYTES`
bounds the list. The quota is checked before a write and, for a new file, again
once its bytes are on disk, so concurrent new files never stay over the limit.
A replacement (`replace=true`) is checked only before it lands, so two
simultaneous replacements by one user can overshoot by the growth of one file.
A replacement is staged as a hidden `.upload-*.part` file; one left by a crash
is invisible to the user and to the quota, and nothing removes it.

**Fix:** add `limit`/`offset` to the listing; take a per-user lock (database row
or `flock`) around a replacement; sweep stale `.part` files on startup.

### 5. PDF artifacts: italics, CJK and right-to-left text

The image's `fonts-dejavu-core` has no italic face, so italics in a PDF print
upright (Word files keep them). DejaVu Sans covers Latin, Greek, Cyrillic and
more, but not Chinese, Japanese or Korean, which print as boxes; Arabic and
Hebrew print unshaped and left to right. A deployment without the font falls
back to Helvetica: Western European text only.

**Fix:** point `PDF_FONT_PATH` / `PDF_BOLD_FONT_PATH` at a family that covers the
scripts you need (for example Noto), add an italic font setting, and enable
ReportLab's optional shaping extras for right-to-left text.

### 6. Approval gates: what they leave out

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
- **The compatibility endpoint waits.** `POST /pipelines/<id>/run` and chat's
  `run_pipeline` wait for a run's end, so one that asks keeps its caller waiting
  until the owner answers on the Runs page, at most `RUN_WAIT_MAX_SECONDS` (300):
  the endpoint then answers `202 run_still_running` and the run goes on. A run
  waiting for an answer also keeps its executor slot (`RUN_MAX_CONCURRENT`) the
  whole time; `RUN_MAX_ACTIVE_PER_USER` keeps one account from holding them all.

**Fix options:** per-tool "always allow" rules saved with the integration; a
`requires_approval` flag in `GET /agent-tools` so the builder can show which
tools will ask; pausing the step's timeout clock while it waits; push or email
notifications for waiting runs; letting chat ask inline.

### 7. Runs execute inside the API process

The run executor (`api/services/run_executor.py`) is an asyncio loop in the API
process, and its queue lives in memory. That is enough for the single
container this deploys as, but a second process (another replica or Uvicorn
worker) would not share the queue, and its start-up recovery
(`repositories/active_runs.interrupt_active`, which takes every active run in
the database for one the previous process left) would mark the first process's
active runs as interrupted, while they go on executing there. The guard that
keeps a resume from overlapping a stopped attempt still winding down
(`RunExecutor.settled`) is in memory too. A restart interrupts the runs in
progress; they have to be resumed by hand. Run progress is polled (every 1.5 s
per open run), not pushed.

**Fix:** when more than one process is needed, move execution to a worker
behind a shared queue (the `RunExecutor` port is the seam), scope recovery to
the worker that owned a run, optionally resume interrupted runs
automatically, and push progress with server-sent events.

### 8. A run's spending limit is checked between model calls

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
  price). Only a token limit can (`RUN_DEFAULT_MAX_TOKENS`, `RUN_MAX_TOKENS`),
  and the app offers a cost limit; a token limit is set through the API.
- A step's `cost_usd` adds up the calls whose cost is known. If a provider
  reports it on only some calls, the step shows a floor and nothing marks it
  incomplete: a run's `cost_complete` turns `false` only when a step used
  tokens and has no cost at all.
- Chat messages are metered (`CHAT_MAX_TOKENS` bounds one message) but their
  usage is not saved, so `GET /usage` covers pipeline runs only, and the chat
  agent's `run_pipeline` tool starts runs under the server's default limits
  only. A provider that sends no usage in a stream (TogetherAI unless it does
  so by default) leaves a chat message's calls uncounted. The planner
  (generate, revise) is bounded per call (`LLM_PLANNER_MAX_OUTPUT_TOKENS`) but
  not metered either.

**Fix:** refuse a call that cannot fit the remaining budget, from an estimate of
its prompt size and the model's maximum output (a pre-flight check in
`RunMeter.check`); keep a `cost_complete` column on `run_steps` so a partial
cost is visible; save chat and planner usage so `GET /usage` and per-account
daily caps can count it; give the chat tool an optional limit.

### 9. Scheduled runs: what the first version leaves out

Schedules (`api/services/schedules/`) start runs from a thread inside the API
process, so they share every limit of entry 7 above: one process, nothing runs
while it is down. Beyond that:

- **At most once, not at least once.** The scheduler claims an occurrence (moves
  `next_run_at`) *before* it starts the run, so two processes never start the same
  one. A process that dies between the claim and the run being saved loses that
  one occurrence, with no trace on the schedule.
- **Missed times are not replayed.** After downtime an overdue schedule runs once,
  not once per missed time, and there is no "catch up" option. A run starts up to
  `SCHEDULER_TICK_SECONDS` (30 s) after its time.
- **A long run skips times.** A time that comes while the schedule's previous run
  is still queued, running or waiting is skipped, with `last_error` saying so (an
  hourly pipeline that takes two hours runs every other hour). It is not
  queued behind the previous one, and "run now" is not held back by it.
- **Unattended runs and approvals.** A scheduled run has nobody watching it. If one of
  its steps calls a tool that asks first (a tool of an MCP server or an integration
  whose "Ask me before its tools act" switch is on), the run waits for its owner and
  the call counts as declined after `APPROVAL_TIMEOUT_SECONDS` (30 minutes), so the
  agent goes on without it. For a schedule that must act on its own, switch that
  integration's approval off, knowing its tools then act unasked.
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
execution to a worker (entry 7) also moves the scheduler there.

### 10. Conditions and review loops: what the first version leaves out

Conditional steps and review loops
([architecture.md](architecture.md#conditions-and-review-loops)) follow a few
simple rules and leave some things out:

- **Loops cannot share a stage.** A pipeline whose review loops would run the same
  stage (a reviewer inside another reviewer's loop, or two reviewers in one stage)
  is refused when it is saved; loops that follow each other are fine. That is the
  simplest way to keep one round counter per step and a run's length known from
  its pipeline (`loops.recursion_limit`). A run whose stored data breaks the rule
  follows the earlier loop and ignores the later one, with a warning in the log.
- **A verdict has to be alone on its line.** A reviewer is asked to end with
  `VERDICT: PASS` or `VERDICT: REVISE`. A verdict inside a sentence, a line with
  other words, or no verdict at all counts as "carry on", never as an error, so a
  reviewer that forgets the line cannot stop a run (nor send the work back). The
  feedback a step receives is the reviewer's whole answer, however long.
- **The stage after a reviewer gets the reviewer's answer**, as after any step, not
  the work it judged. Mark the step whose work is reviewed as the output (the
  planner is told to), or ask the reviewer to repeat the approved work in full.
- **A skipped last stage leaves nothing to show.** A skipped step is never a
  deliverable; when every step that makes the outputs is skipped the run still
  succeeds, with no outputs (the page says why) and the text it was handed as its
  final answer.
- **Progress can go back.** "3 of 5 steps done" falls when a step is redone in
  another round, because the step is running again.
- **A resumed run can lose one thing.** A step that shares the reviewer's stage and
  places `{feedback}` in its own prompt is given an empty `{feedback}` when the run
  stopped after the reviewer began the next round but before that step did (the
  reviewer's earlier answer is replaced as it starts). Steps in the stage the work
  goes back to, and in the stages between, are never affected.
- **Names and numbers, not links.** A condition names a step by its number and a
  review a stage by its number. The builder follows renumbering and new stages, and
  a condition whose step was removed is left pointing at "step 0" and flagged, but
  the planner writes the numbers itself and can get them wrong; the save-time
  check drops what cannot work from a plan.
- **`feedback` is a reserved input name**, like `input`. A pipeline saved earlier
  with an input of that name still runs (its input wins over the reviewer's
  feedback in that pipeline's prompts), but it has to be renamed to be saved again.
- **Downgrading the database** (`alembic downgrade`) turns `skipped` steps into
  `succeeded` ones with an empty output, because the older code has no such status,
  and drops the conditions, review loops and rounds.

**Fix options:** allow loops inside loops by keeping the round counter per loop
instead of per step, and size the step limit from the nesting; keep the reviewer's
answer on the loop instead of in the reviewer's row (a `run_loops` table) so a
resume never loses it; let a condition and a review name a step by its id, and
renumber nothing; show a redo as its own count in the run header.


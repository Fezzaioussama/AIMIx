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
thread, with the native parsers (pypdf, PDFium, Pillow, lxml) in the server's own
process. Each step is bounded (size, page, row, pixel, XML-part and character
limits, `DOCUMENT_OCR_TIMEOUT_SECONDS` per OCR'd page and
`DOCUMENT_OCR_MAX_SECONDS` per document), and at most
`DOCUMENT_MAX_CONCURRENT_EXTRACTIONS` documents are read at once for people
(`DOCUMENT_AGENT_MAX_CONCURRENT_READS` more for agents, whose OCR all runs in the
same process and on the same CPUs), but nothing
can interrupt a parser mid-call: a long scan still holds a worker for about two
minutes, which conflicts with AGENTS.md §6 ("no long-running work in the request
path"), and pypdf's text layer has no time limit of its own. PDFium rendering is
serialised across the process (it is not thread-safe); a page that waits past
`DOCUMENT_EXTRACTION_WAIT_SECONDS` for it is skipped, but the page being
rendered cannot be stopped. An Office file is refused only when one part is over
`DOCUMENT_MAX_XML_PART_BYTES`, so several parts just under it (up to
`DOCUMENT_MAX_UNPACKED_BYTES` in all) are parsed whole: about 20 MB of memory per
MB of XML at worst.

Not read at all: legacy binary Office files (`.doc`, `.xls`, `.ppt`), `.xlsm`,
SmartArt and chart text in slides, handwriting beyond what Tesseract manages,
and the values of a form that keeps them only in XFA (no AcroForm field).

How PDF scans are recognised: a page with no text layer, or with under
`DOCUMENT_OCR_MIN_PAGE_CHARS` (50) characters of small print (14 pt or less, so
not a slide's title) while pictures cover most of the page, goes to OCR, whose
text follows the page's own. A scan drawn inside a form XObject, one whose text
layer holds 50 characters or more (a long scanner footer), or one stamped in
larger print, is not recognised, so only its text layer is read; a photo page
with a short small-print caption is OCR'd for nothing, which costs OCR time and
OCR's per-document page budget (still bounded by `DOCUMENT_OCR_MAX_PAGES` and
`DOCUMENT_OCR_MAX_SECONDS`). Each agent call that reads a scan runs OCR again: a
scan two agents read, or one read in several calls, is recognised again each time
(nothing is cached). A form field is labelled with its tooltip, else its
internal name, which some forms make cryptic (the IRS W-9 says `f1_01[0]`).

Agents (`read_workspace_file`) read a PDF in whole pages of up to
`WORKSPACE_MAX_OUTPUT_CHARS` per call, reading on with `start_page`: one page
longer than that on its own is cut, and the rest of that page cannot be reached.
The page that did not fit is read, and OCR'd if it is a scan, by both the call
that stopped before it and the next one. A call stops before a page OCR's
per-call page or time budget would skip, so the next call reads it. Other files
are read in parts of
`WORKSPACE_MAX_OUTPUT_CHARS`, so a Word or Excel file is read again, up to
`DOCUMENT_MAX_CHARS`, for every part.

**Fix:** run extraction as a background job in worker processes (a process per
render also lifts the PDFium lock) with a wall-clock timeout and let the client
poll, and cap request bodies at the reverse proxy as well. For PDFs: follow
pictures into form XObjects, read XFA form data, and let an agent read on inside
one long page (a character offset next to `start_page`).

### 3. Integrations: what the first version leaves out

Users' own MCP servers (`api/services/integrations/`) work with static headers
only. Their URLs are stored as entered, so a service that puts its token in the
URL keeps it unencrypted at rest (header values are encrypted). A tool call
that fails at the connection level stops the run, as for `MCP_SERVERS`, instead
of reaching the agent as an error result. "Test connection" results live only
in the open page.

**Fix options:** encrypt the URL and show only its host; support the MCP OAuth
flow; a tool interceptor that turns a failed call into an error result; store
the last test's time and tool count.

`POST /files` has the same request-size guard, and an agent reading a PDF or
Word file from its workspace runs the same readers in the agent's thread.

### 4. Files: no pagination, and a narrow quota race on replacement

`GET /api/files` returns every file a user has; only `WORKSPACE_MAX_TOTAL_BYTES`
and `WORKSPACE_MAX_FILES` bound the list. A new file is counted against the quota
once its bytes are on disk, so concurrent new files never stay over the limit.
A replacement (`replace=true`) is checked only before it lands, so two
simultaneous replacements by one user can overshoot by the growth of one file.
Each save walks the user's whole folder to count the quota (once), which
`WORKSPACE_MAX_FILES` keeps short.

**Fix:** add `limit`/`offset` to the listing; take a per-user lock (database row
or `flock`) around a replacement.

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
  `save_artifact`, `run_python`, `generate_image` and the workspace tools act
  unattended unless `AGENT_APPROVAL_TOOLS` names them.
- **A picture's price is not in the run's cost.** `generate_image` spends $0.01 and
  `find_objects` $0.0025 of the user's Meta credit per picture, but only model
  tokens count toward a run's `cost_usd` and its spending limit; the agent's
  recursion limit is what bounds how many pictures one step can use.
- **A step cannot be approved ahead of time**, and the builder does not mark
  which tools will ask. The wait counts toward the step's `AGENT_TIMEOUT_SECONDS`,
  and a restart expires the requests (a resumed run asks again).
- **Waiting is polled.** A run reads the database about once a second
  (`APPROVAL_POLL_SECONDS`) and the page polls the run every 1.5 s, so an answer
  takes up to a second or two to show. Beyond the Runs
  tab's count, the owner is emailed once per step that asks (`SMTP_*`); there is
  no push notification.
- **The compatibility endpoint waits.** `POST /pipelines/<id>/run` and chat's
  `run_pipeline` wait for a run's end, so one that asks keeps its caller waiting
  until the owner answers on the Runs page, at most `RUN_WAIT_MAX_SECONDS` (300):
  the endpoint then answers `202 run_still_running` and the run goes on. A run
  waiting for an answer also keeps its executor slot (`RUN_MAX_CONCURRENT`) the
  whole time; `RUN_MAX_ACTIVE_PER_USER` keeps one account from holding them all.

**Fix options:** per-tool "always allow" rules saved with the integration; a
`requires_approval` flag in `GET /agent-tools` so the builder can show which
tools will ask; pausing the step's timeout clock while it waits; push
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
progress; the next startup resumes them by itself (`RUN_AUTO_RESUME`), but the
work of a step in progress is done again, and a run interrupted longer ago
than `RUN_AUTO_RESUME_MAX_AGE_SECONDS`, or whose owner has no key, waits for
its owner. Run progress is polled (every 1.5 s per open run), not pushed.

**Fix:** when more than one process is needed, move execution to a worker
behind a shared queue (the `RunExecutor` port is the seam), scope recovery to
the worker that owned a run, and push progress with server-sent events.

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
- Chat messages and planner calls are saved as usage events and count toward
  `GET /usage` and the server key's daily allowance, but the chat agent's
  `run_pipeline` tool still starts runs under the server's default limits only,
  a provider that sends no usage in a stream (TogetherAI unless it does so by
  default) leaves a chat message's calls uncounted, and a usage event records
  the profile's default model even when the planner was asked on another
  (`planner_model`).

**Fix:** refuse a call that cannot fit the remaining budget, from an estimate of
its prompt size and the model's maximum output (a pre-flight check in
`RunMeter.check`); keep a `cost_complete` column on `run_steps` so a partial
cost is visible; give the chat tool an optional limit.

### 9. Scheduled runs: what the first version leaves out

Schedules (`api/services/schedules/`) start runs from a thread inside the API
process, so they share every limit of entry 7 above: one process, nothing runs
while it is down. Beyond that:

- **A lost occurrence is replayed at the next start only.** The scheduler claims
  an occurrence (moves `next_run_at`) *before* it starts the run, so two processes
  never start the same one, and keeps the claim until the run is saved, so a
  process that dies in between starts it at its first tick after the restart. A
  run saved just before the death is not started twice; a "run now" of the same
  schedule meanwhile counts as that run too.
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
  times and no switching off after repeated failures (the owner is emailed when
  the reason changes); a
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

**Fix:** add an
"only when the last run is finished" option and a `schedule_id` filter on
`GET /api/runs`; keep the last few start failures and pause a
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
- **The final check sees the last stage only.** The orchestrator every new team
  ends with receives what the stage before it produced, like any reviewer. When the
  deliverables are made in several stages, it checks the last ones; the earlier
  ones still show in the results, unchecked. It sends work back at most twice,
  so a run of a new team can cost up to three times its deliverable stages.
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

### 11. Web pages read from a link: what the first version leaves out

`POST /documents/import-url` (`api/services/documents/web_import.py`) reads a page
the way a browser would download it, not the way it would show it:

- **Pages built by JavaScript.** The server never runs a page's scripts, so a page
  that builds its text in the browser (Excalidraw, most social networks, many
  dashboards) holds almost nothing. Under `DOCUMENT_URL_MIN_TEXT_CHARS` (200
  characters) it is refused with advice to paste the text or attach the page
  printed to PDF. A script-built page whose shell has more text than that (a long
  cookie banner, a footer) passes with the shell only, and a real page shorter than
  that is refused.
- **A schedule keeps the page as it was.** The text is read once, when the user
  adds the link, and travels in the run input like an attached document's. A
  schedule repeats that text on every run and never reads the page again, so one
  meant to follow a page that changes (prices, news) works on the old text.
- **No sign-in.** No cookie or credential is sent (a link, or a redirect, with a
  user name or password is refused), so a page behind a sign-in, a paywall or a bot check gets a
  502 advising to save it as PDF; a site that answers 200 with a sign-in or consent
  page instead gets that page read.
- **What decides the format and the charset.** Only the `Content-Type`, and for
  bare bytes a `%PDF-` signature or the link's extension: a file named only by
  `Content-Disposition` (a `.docx` sent as `application/octet-stream` from
  `/download?id=7`) is refused (415). Charset labels are Python's, not the HTML
  standard's, so a page labelled `iso-8859-1` that uses Windows-1252 quotes gets
  control characters for them.

**Fix options:** read a link input again when a manual or scheduled run starts
(never from chat), with the same address checks; render script-built pages in a
headless browser run as a separate, sandboxed service; take a file's name from
`Content-Disposition`; map charset labels as the HTML standard does.


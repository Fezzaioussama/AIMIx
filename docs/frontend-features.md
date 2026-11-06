# Frontend features

One section per folder of `frontend/src/features/`. The shared layers (`core/`,
routing, the gateway, conventions and the test list) are in
[frontend.md](frontend.md); the Missions workspace and the run report every run
screen shares in [frontend-missions.md](frontend-missions.md).
### `features/mission`

The Missions workspace at `/mission` and `/mission/<pipeline id>`: the conversation, the
team, the results, their layouts and what is kept. It has its own page,
[frontend-missions.md](frontend-missions.md#featuresmission--the-missions-workspace),
with the run report the Results pane shares with the Runs page and the builder.

### `features/chat`

The Chat screen at `/chat`, over the chats the server keeps: the list, the open chat,
its replies' tools and cost, and what the tab remembers. It has its own page,
[frontend-chat.md](frontend-chat.md).

## `features/pipelines`

| File | Role |
|---|---|
| `PipelineBuilderPage.tsx` | Builder screen: saved list, name, run inputs, steps, then the diagram, the run form and the latest run; under its title the foldable "Ask AIMIx to change this pipeline" and "Schedule this pipeline" ([`features/schedules`](#featuresschedules)) panels. It follows the open pipeline's newest run (`features/runs/useFollowedRun`): the diagram shows that run's live step statuses when the run executed exactly the version on screen; under the run form, "Starting the run…" while a run starts, then the region "Latest run" with its [run report](frontend-missions.md#the-run-report-featuresrunsreport) at level 2 ("Open in Runs", and "This run used an earlier version of this pipeline." for a run of another version). `<main>` scrolls inside itself only from `xl`, where the editor sits beside the canvas (below, the window scrolls, so the report's title rows stick below the 60px top bar); its vertical padding sits on the inner column, so a stuck row meets the scroller's top edge. Leaving the page does not stop a run; reopening the pipeline shows it again |
| `AttachDocument.tsx`, `useAttachDocument.ts`, `AttachWebPage.tsx`, `WebPageField.tsx`, `DocumentStatus.tsx`, `attachStyles.ts` | The controls under every run input (builder, mission conversation, schedule form). "Attach a document": choose a PDF, Word, Excel, PowerPoint, image, HTML, CSV or text file (the picker's `accept` and the helper text both come from `DOCUMENT_FORMATS`). "Add a web page" (`AttachWebPage`): a button that reveals `WebPageField` — a `type="url"` field, "Read page" or Enter reads (https:// added when left out; Enter never submits a surrounding form), Escape closes, and focus goes back to the button; it opens with a 250 ms grid-row and opacity reveal and is `inert` while closed. The server reads either (`core/api/documents.ts`) and the text is added to the input under a `[Document: name or address]` line, where it stays editable. `useAttachDocument(target)` is one hook with two loaders (`readFile`, `readPage`) sharing one reading, error, notice and cancellation: it reads the target when the document *arrives* (so text typed meanwhile is kept), replaces a read still going, and cancels on unmount. An input that holds only a link shows "Agents can’t open links on their own." with "Read this page into the box", whose page takes the link's place (`placeDocument`). A document that would put the run past `RUN_INPUT_MAX_LENGTH` is held with a warning (an alert) until "Add it anyway" or "Leave it out". `DocumentStatus` is the line under the controls: a polite live region ("Reading report.pdf…", then what was added), the server's reason as an alert; after "Add it anyway" or "Leave it out" focus goes back to the picker. `onReading` tells the form what is being read, so it can wait. The controls are at least 44px tall on a phone |
| `RecentPipelines.tsx`, `RunInputCard.tsx` | The builder's saved-pipeline list and its "Run Execution" panel: one labelled field per named input (all required), or a single free-text field when the pipeline declares none, then the optional cost limit. `RunInputCard` exports `RunInputFields` (those fields alone, with "Attach a document" and "Add a web page"; an optional `label` names the free-text field), which the schedule form asks its inputs with too, naming it "Input for each scheduled run" so the builder page never holds two fields called "Run input". Inputs past `RUN_INPUT_MAX_LENGTH` in all are said under the fields ("Your inputs are 612,000 characters; a run takes at most 500,000. Shorten the text, or delete a document from it (each starts with “[Document: …]”).", a polite status, there even when empty so it is announced, since the count changes with each key) and the run waits. While any input reads a document or page (`useInputReadings`, told by each `AttachDocument`), or one is read elsewhere for the run (`waitingFor`: the mission's message box), Run waits and says "Waiting for report.pdf to be read…"; the schedule form's save waits the same way. The `documents` input shows how to fill it ("Attach your documents or web pages below, or paste their text.") instead of its description, which says AIMIx puts their text there |
| `CostLimitField.tsx` | The "Stop if it costs more than $…" field of the run form: optional, labelled, with its hint or problem under it as a polite live region. The draft keeps it as typed text (`RunDraft.maxCost`); `costLimitProblem` flags text that is not an amount above zero and `isRunReady` then blocks the run, because running without the cap the person asked for would be worse than not running. `runRequest` sends it as `max_cost_usd` |
| `FoldablePanel.tsx` | `PanelToggle` (the bar: a heading holding one button with an icon, a title, an optional `summary` and a chevron that flips, `aria-expanded` / `aria-controls`), `Foldable` (the body, animated by its grid row with a fade and a 2px blur, `inert` while folded; `size` small opens in 250 ms and closes in 150, large in 350 and 250; `bodyClassName` replaces its padding) and `DisclosureButton` (an inline text button that opens a `Foldable`: "Read the full check"; its `id` lets a jump hand focus back to it). `RevisePanel`, `SchedulePanel` and the run report are built on them |
| `usePipelineBuilder.ts` | State + transport: pipeline, saved list, dirty state, and actions for editing steps and inputs, adding parallel or following stages, replacing the whole draft (`replace`, for an accepted revision), saving and starting a run (`run` returns the started run for the page to follow). A changed pipeline must be saved before running. |
| `AutoPipelinePage.tsx` | Describe (typed or said with the microphone) → generate → preview diagram → refine it in a sentence → edit inputs and steps → save |
| `useAutoPipeline.ts` | Generation, editing (including the planned inputs), adding or removing output steps, `replace` (an accepted revision) and saving the proposed workflow (later saves update it) |
| `RevisePanel.tsx` | "Ask AIMIx to change this pipeline": a foldable panel (open by default on the auto page) with the change box, clickable example instructions, a microphone to say the change, a busy line with Stop, and the review. Ctrl/⌘ + Enter asks. Apply hands the revision to `onApply` (the page replaces its draft and leaves it unsaved); it never saves. Props: `pipeline`, `onApply`, optional `plannerModel`, `disabled`, `defaultOpen`, `headingLevel`. Mounted under the builder's title and under the auto page's diagram |
| `RevisionReview.tsx` | A proposal: the change list in plain words (added / changed / removed marks), a `PipelineGraph` preview, Apply and Discard; "Nothing to change" when the planner changed nothing. `ChangeList` is exported: the mission conversation shows the same list |
| `useRevisePipeline.ts` | `useRevisePipeline(pipeline)` → `{ proposal, stale, busy, error, propose, cancel, discard }` over `POST /api/pipelines/revise`. The proposal keeps the draft's id (so a save updates it) and only applies to the draft it was made from: an edit sets it aside (`stale`), and an answer for a draft edited meanwhile is dropped. Aborts on unmount and on `cancel` |
| `useRevisePanel.ts` | The panel's own state over `useRevisePipeline` (typed instruction, applied flag, `edit` / `pick` / `ask` / `apply` / `discard`) and `panelStatus`, the text of its live status line |
| `revision.ts` | `describeChange` (a change as a sentence), `adoptRevision`, the example instructions and the instruction length limit (mirrors the backend's) |
| `buttonStyles.ts` | Primary and secondary in-card button looks for actions beside a page's GlowButton |
| `PipelineInputsEditor.tsx` | The named run inputs (name, label, description), shared by both screens; names are typed as snake_case and problems show before saving |
| `pipelineInputs.ts` | Pure helpers for named inputs and attached documents (`appendDocument`, `placeDocument`, `documentSummary`, `documentDetails`, `documentSize`, `documentLimitWarning`, and `splitDocuments`, which reads an input back into its typed text and its `[Document: …]` blocks, with the same separator `appendDocument` writes): the naming rule (mirrors the backend), `{placeholder}` checks, the run form's `RunDraft`, `inputValue` (what the person typed, else the input's `default_value`, so a mission's form starts filled in with what its request gave), `runRequest`, which sends only declared inputs, and the run's size limit, `RUN_INPUT_MAX_LENGTH` (500,000 characters in all, mirroring `backend/api/schemas/common.py`): `runInputSize` (what `runRequest` sends, defaults included), `runInputLimitProblem`, and `isRunReady`, which is false past it; `waitingForDocument`, the words for anything that waits for a reading |
| `webLinks.ts` | Pure: the http(s) links in typed text (`linksIn`, without the punctuation after them), a field holding only a link (`bareLink`), a typed address made openable (`toWebAddress`), `sameAddress`, and short names for links (`linkLabel`: host and path without `https://` or `www.`, cut in the middle; `linkHost`; `sourceLabel`, a file's name or a page's label) |
| `StepEditor.tsx` | Builder sidebar: each step's stage, title, expected output, agent role, tool access, model, prompt and, folded away, the two options that change how work flows (`StepFlowFields`). `StepCard` (one step's editor; it takes every step of the pipeline too) is exported: the mission screen's drawer uses it |
| `StepFlowFields.tsx`, `ConditionFields.tsx`, `ReviewFields.tsx`, `FlowFieldParts.tsx` | Two `<details>` sections, folded by default (the first file holds the sections, the next two their fields, the last the labelled field and the problem line they share): "Run this step only if…" (a source list: the previous result, each input, each earlier step by title; a comparison; the text, hidden for "is empty" / "is not empty") and "Review loop" ("Send the work back to stage [2 · Writer] up to [2 times] when this step says the work needs fixes", offered to a step with an earlier stage, plus one line saying its prompt should judge the work). Each shows what is set next to its title, and what is wrong in amber (`aria-invalid`, `aria-describedby`); a source or stage that is no longer on offer stays in its list, so the person sees what it was. Used by the step card (builder and the mission drawer) and by the planned steps |
| `stepFlow.ts`, `stepFlowProblems.ts`, `stepFlowEdits.ts`, `flowSources.ts` | The flow helpers. `stepFlow.ts`: the `CONDITION_OPERATORS` registry (the six comparisons in plain words), the limits (they mirror the backend's), `conditionSources`, `describeCondition` / `describeReview`, `reviewLoops` / `roundTotals` (which loops the engine follows and how many rounds each step may take: loops that cannot work or share a stage are dropped as the engine drops them). `stepFlowProblems.ts`: `conditionProblem` / `reviewProblem` in plain words (`SOURCE_CHECKS` is a registry like the engine's). `stepFlowEdits.ts`: editing renumbers steps and moves stages, and a condition names a step by number and a review a stage by number, so `withoutStep`, `followRenumbering` and `followNewStage` keep each pointing where it did (a condition whose step was removed is left looking at `step:0`, a step that does not exist, and the editor says so; nothing is moved onto another step or silently removed). `flowSources.ts` is their import-free leaf |
| `PromptPlaceholders.tsx` | Under a prompt: `{input}`, `{feedback}` (a reviewer's feedback when work is sent back) and the declared `{name}` placeholders, plus a warning for a placeholder nothing fills |
| `StepAgentFields.tsx` | Agent role and tool policy controls shared by manual and generated step editors (`null` all, `[]` none, selected names otherwise); the checklist groups tools by source, so an integration's tools sit under its name |
| `StepRoleFields.tsx` | A step's title, its Intermediate / Output toggle and its expected output, shared by both editors |
| `GeneratedSteps.tsx` | Generated steps drawn stage by stage; parallel steps side by side; each step shows the condition or review loop the planner gave it, editable like in the builder |
| `PipelineGraph.tsx`, `GraphNodeCard.tsx` | Flow diagram Input → stages → Outputs with fork/merge brackets, a legend and controls to add parallel steps or a following stage; the Input terminal lists the named inputs; nodes show title, model, status, an Output badge and their expected output; where the diagram is editable, selecting a node opens its step editor. Stages slide in; during a run connectors pulse and running nodes carry a StarBorder. `NODE_STATUS_STYLES` holds each status's colours and word: Not run, Waiting, Running, Done, Failed, Stopped, Skipped (muted and dashed, with "Its condition was not met" on hover). A step with a condition carries an "Only if…" mark (its words on hover and in its accessible name), a reviewer a "Reviewer" mark, and a step a followed run redid a "Round 2 of 3" mark. The legend explains the marks that are on the diagram |
| `LoopRail.tsx`, `graphLayout.ts` | The line that shows a reviewer sending work back: a row above the stages, from the reviewer's stage back to the stage it goes to, ending in an arrow into that stage with "Back here up to 2 times". It lines up with the columns because both read their widths from `graphLayout.ts` (stage columns have a fixed width), and it hides from assistive technology (the reviewer's node and the legend say the same in words). Drawn only for loops the engine would follow; it scrolls with the diagram on a phone |
| `pipelineGraph.ts` | Pure model behind the diagram (`buildGraph`, which takes a followed run's steps for live statuses and its outputs, and gives each node its condition, review, round and the most rounds it may take; a skipped node is never an output; `liveNodeStatus`) |
| `roundNotes.ts` | `roundLabel`: "Round 2 of 3", the words of a step a review loop ran again (the diagram's mark, the run report's rows) |
| `stages.ts` | `groupByStage`, `nextStage`, `insertStep` (which keeps conditions and review loops pointing where they did when it renumbers steps or opens a stage), `outputOrders` (preview of which steps are outputs; mirrors the backend rule) and `stepLabel` |
| `fieldStyles.ts` | The builder's field looks (`FIELD`, `INLINE_FIELD`, `SMALL_ACTION`) |
| `StageInput.tsx`, `StageHeader.tsx`, `StageArrow.tsx` | Stage picker, stage label ("N steps in parallel"), connector |
| `OpenInMissionLink.tsx` | On the builder's title, for a saved pipeline: "Open in mission view" (`/mission/<id>`); with unsaved edits it asks to save first instead |
| `modelLabel.ts` | Human-friendly label for a model id |

### `features/templates`

The template gallery at `/templates`, reached from Templates in the sidebar
and the "Start from a template" link on Auto Pipeline. Using a
template creates the user's own pipeline on the server, then opens it in the
builder through the same `{ pipelineId }` router state Auto Pipeline uses
(the window is scrolled to the top first, since routes keep the scroll).

| File | Role |
|---|---|
| `TemplatesPage.tsx` | Header, category chips, the card grid, a polite live region for "Creating your pipeline…", and alerts for a failed load (with "Try again") or a failed use |
| `useTemplates.ts` | Loads the gallery (cancelled on unmount, reloadable) and `create(template)`, which resolves to the new pipeline or `null` with a message saying which template failed |
| `TemplateCard.tsx` | Icon, category, title, description, "You provide:" (the input labels), agent and stage counts, and "Use this template" (busy spinner; disabled while any template is being created) |
| `CategoryFilter.tsx` | `aria-pressed` chips: "All", then each category as it first appears |
| `templateFilters.ts` | Pure `categoryChips` and `inCategory` |
| `templateIcons.ts` | Card icon by slug; a template the server adds later gets a generic icon |
| `StartFromTemplateLink.tsx` | The link into the gallery, used on Auto Pipeline |

### `features/files`

The user's workspace: what their agents save and what they upload for agents
to read (`/api/files`).

| File | Role |
|---|---|
| `FilesPage.tsx` | Header with the storage used (text and a bar), the upload panel, an `aria-live` status line, then the list or the empty state ("Files your agents save appear here. Agents with file tools can also read the files you upload.") |
| `UploadPanel.tsx` | Drop zone plus a "Choose files" `GlowButton` that opens a hidden multi-file input (`accept` from the server's `allowed_extensions`), the accepted types in plain words and the size cap, and each refused file with its reason; a taken name offers "Replace". The drop zone is `core/hooks/useFileDrop`, dark and ignoring drops while a file is on its way up |
| `FileRow.tsx` | One file: type icon (lucide), name, folder, size, date, download and (when `onDelete` is given) delete buttons with a spinner while busy, 44px under a finger; delete asks first (focus starts on Cancel, Escape cancels) and errors show under the row. An optional `preview` sits above it (the run report's pictures) |
| `PicturePreview.tsx` | A workspace picture shown through `useImagePreview` (`alt=""`: its name follows), with a hairline outline; the caller sizes it |
| `useFiles.ts`, `fileDownload.ts` | State + transport: loads the listing, uploads one file per request (so each refusal is reported against its file), replace/dismiss, download (`downloadAndSave`: the file, then `saveBlob` from `core/saveBlob.ts` under its own name, nothing once aborted) and delete (a 404 counts as deleted). One `AbortController` per mount (`useLifetime`, also used by the run report's files) cancels everything on unmount |
| `fileFormat.ts` | Pure helpers: `formatBytes` (decimal units like the server's limits), `formatDate`, `fileName`, `folderOf`, `fileIcon`, `describeTypes`, and `withFile` / `withoutFile`, which keep `used_bytes` equal to the sum of the sizes |

### `features/runs`

Runs execute on the server; the screens follow them by polling. Each screen shows a run
as its run report (`report/`, described with the Missions workspace in
[frontend-missions.md](frontend-missions.md#the-run-report-featuresrunsreport)); the
builder and the Missions workspace follow their pipeline's newest run with the hooks below.

| File | Role |
|---|---|
| `useRun.ts` | `useRun(runId)` → `{ run, error, busy, stop, resume(budget?), approve, decline, adopt }` (`RunControls` is the part a run report needs). Fetches the run, polls it every `RUN_POLL_INTERVAL_MS` (1.5 s) while it is queued, running or waiting for an approval and stops once it ends; unmounting or switching runs clears the timer and aborts the request in flight. A resumed run is polled again; `approve(approvalId)` and `decline(approvalId)` answer a request and show the run as it comes back; `adopt(run)` shows a run already in hand (one just started) at once. A failed poll is retried, a 404 is not |
| `useLatestRun.ts` | The builder's and the mission's follower: loads the pipeline's newest run when it opens (`GET /runs?pipeline_id=…&limit=1`) and `follow(run)` switches to a run started here; `checked` once it is known whether there is a run to follow (and it has loaded), `listed` for a run found that way rather than started here |
| `useFollowedRun.ts` | What the builder and the mission need from that run: whether one is active, and the run the diagram may show (`shown`, only a run of exactly the version on screen) |
| `useRunHistory.ts` | The history list: pages of `RUN_PAGE_SIZE` (20), refreshed every `RUN_LIST_REFRESH_MS` (5 s) while a listed run is active; `update` keeps a line in step with the open run, `remove` deletes a run |
| `report/` | **The run report**, one run as one document: `<RunReport key={run.id} run control level extras />`, the same on the Runs page, in the builder and on a mission. See [frontend-missions.md](frontend-missions.md#the-run-report-featuresrunsreport) |
| `toolWords.ts` | `TOOL_WORDS`, a registry of each tool's use in words: `toolUsePhrase` ("1 date check · 3 web searches · 3 page reads, 1 failed"; a tool it does not know reads by its name), and the plain request an approval makes (`approvalAsk`, `approvalHeading`: "Save “notes/plan.md” to your files?") for AIMIx's own tools (`isPlainAsk`, `fromSource`) |
| `RunCost.tsx` | The run's cost in the report's meta line: `$0.0123` (its token counts a hover away, and read out), "$0.0123 or more" when part of it is unpriced, "Cost unknown for this model" when none is, next to "of $0.50 limit" when the run has a limit; nothing before an active run has used anything (or "Limit $0.50" if it has one), and "No usage recorded" for a finished run with none |
| `ResumeControl.tsx` | The Resume button. A run that stopped at its spending limit cannot resume under it, so it shows "Raise the limit to $[ ] Resume" instead, prefilled with double the old limit, saying what the run has used so far and refusing an amount at or below that; the token variant appears when it was a token limit. `onResume(budget?)` carries the new limit |
| `runBudget.ts` | `limitReached(run)` (which limit a run is at; mirrors the server's rule, rounding slack included), `limitParts`, `suggestedLimit`, `limitBudget` and `limitProblem` for the resume form, and `BUDGET_ERROR_CODE` |
| `PendingApprovals.tsx`, `ApprovalCard.tsx`, `ArgumentList.tsx`, `approvalFormat.ts` | Approval gates. `PendingApprovals` lists a run's `pending_approvals` under the report's header (the report's `Announcer` says how many wait; `askedBy` names the step and role that asks), each as an `ApprovalCard`: its question first (`Allow “Send email”?`, or for AIMIx's own tools a plain one, "Save “notes/plan.md” to your files?"; focusable, `id="approval-{id}"`, the target of "Review the request"), who asks ("Draft (Writer) wants your OK first.") and from which integration, the tool's description (not for a plain ask), what it will use (`ArgumentList`: one labelled value per argument, a long one folded behind "Show all" in a native `<details>`), **Approve** and **Decline** with "Approving…" / "Declining…" states, and "{time left} · No answer counts as a decline." (ticking, `useNow`). `approvalFormat.ts` holds the pure helpers (`toolLabel`, `argumentRows`, `formatTimeLeft`: "5 h 56 min left") A request of kind `question` (an agent's `ask_user`) renders `QuestionCard.tsx` instead: the question as its heading, who asks, the suggested answers as buttons, a box for an answer of their own with Send answer, Skip, and "No answer counts as skipping it." (`TimeLeft.tsx`, shared with the approval card); `useRun().answer` sends it. |
| `useWaitingRuns.ts` | `useWaitingRuns()`: how many runs wait for the person, fetched on mount and every `WAITING_RUNS_POLL_MS` (5 s) with `countWaitingRuns`; a failed fetch keeps the last count, and unmounting clears the timer and aborts the request. The sidebar shows it as a badge on Runs, with the same count in words for screen readers |
| `RunStatusBadge.tsx` | A run status as a pill; `RUN_STATUS_STYLES` holds the words (Queued, Running, Waiting for you, Done, Failed, Stopped, Interrupted) and colours; "Waiting for you" is the one amber, pulsing pill of an active run |
| `runButtons.ts` | `RUN_BUTTON`: the looks of the run controls (stop, resume, neutral, danger): 40px tall, 44px under a finger, a slight press (`active:scale-[0.96]`, none under reduced motion) and the focus ring |
| `runStatus.ts` | `isActive` (queued, running, waiting), `isResumable` (mirroring the backend's status sets), `finishedStepCount` (succeeded or skipped), and `ranThisVersion(run, pipeline)` — whether a run executed exactly the pipeline on screen, conditions and review loops included |
| `RunTriggerTag.tsx` | A small icon and "Scheduled" or "From a webhook" for a run a schedule or another app started (`TRIGGER_TAGS`, `hasTriggerTag`); nothing for any other run. Shown beside the date in `RunHistoryList` and in `RunByline` |
| `RunByline.tsx` | The line under a run's title in `RunDetail`: "Run #12 · Started Oct 24, 9:58 PM · Scheduled · Open the pipeline" (the tag only for a run a schedule or a webhook started, the link only while the pipeline exists) |
| `RunsPage.tsx`, `RunHistoryList.tsx`, `RunDetail.tsx`, `DeleteRunButton.tsx` | The Runs screen: the list (pipeline, status, start, duration and cost) beside the open run on wide screens, one at a time on a phone (with "← All runs"); the detail is the pipeline's name (h2, under the page's h1 "Runs") and its byline, then the run's report at level 3 with the team's diagram in its appendix (the column sets `--sticky-top` to 60px below `lg`, where the window scrolls under the top bar, and 0 from `lg`); Delete asks "Delete this run for good?" with Keep focused, and is offered only once the run has ended |

### `features/schedules`

Runs that start on their own (`/api/schedules`). Two screens use one form:
the builder's **Schedule this pipeline** panel creates a schedule, and the
**Schedules** screen (`/schedules`) lists, switches, edits,
runs and deletes them.

| File | Role |
|---|---|
| `scheduleDraft.ts` | Pure helpers: `ScheduleDraft` (what the form holds), `FREQUENCIES` (one rule per preset — its label, which fields it asks for, how it reads in words: Strategy + Registry, mirroring the backend's presets), `describeTiming` ("Every Monday at 09:00, Paris time"; hourly names no zone; a day past the 28th adds "or the last day, in shorter months"), `formatNextRun` ("Mon 26 Oct, 09:00" on the schedule's own clock), `timeZoneOptions` (UTC first, then every zone `Intl` knows, and the current one), `withFrequency` (hourly asks for minutes instead of a time), `scheduleProblem`, and `toCreate` / `toPatch` / `draftFromSchedule`. It works out no time itself: when a schedule runs is the server's rule |
| `ScheduleFields.tsx` | The timing fields: Repeat, Day of the week (weekly) or Day of the month (monthly), Time (or Minutes past the hour when hourly) and Time zone. Native `time` and `select` controls with `color-scheme: dark`; every control labelled |
| `ScheduleForm.tsx` | The form both screens share: the fields, a live `role="status"` summary (the timing in words, then "Next run: …"), the run inputs asked like a manual run's (`RunInputFields`, under a "What each run is given" legend), a problem shown as an alert only after a first try, and an optional `blocked` reason that disables saving (as does a document still being read into an input). It keeps its own draft, starting from `initial`; give it a `key` to start over |
| `useSchedulePreview.ts` | `useSchedulePreview(timing \| null)` → `{ nextRunAt, error, loading }`: asks `POST /api/schedules/preview` once the timing has stayed put for `PREVIEW_DELAY_MS` (300 ms), aborts a request a newer timing makes obsolete or the screen leaving, ignores an answer that arrives after its request was dropped, and asks nothing for an incomplete timing |
| `SchedulePanel.tsx`, `useCreateSchedule.ts` | The builder's foldable panel (built on `FoldablePanel`, mounted under `RevisePanel`). Its body is built when first opened (a page that never opens it asks the server nothing) and starts afresh for another pipeline. An unsaved pipeline is told to save first; unsaved edits disable saving ("a schedule runs the saved version"). `useCreateSchedule(pipelineId, inputs)` → `{ busy, error, created, create }`: after a schedule is created the form is replaced by a fresh one, so one press never saves it twice, and leaving drops the request |
| `SchedulesPage.tsx`, `useSchedules.ts` | The Schedules screen: loading, an empty state that points to the builder, and the list; each outcome appears as a notice above the list, so a refusal is never below the fold. `useSchedules()` → `{ schedules, status, notice, actions }` with `update`, `setEnabled`, `remove` and `runNow` (which resolves to the started run, or `null`), over the settings' `useSubmission` (one busy flag, one notice). The list is fetched again every `ACTIVE_REFRESH_MS` (5 s) while a listed last run is queued or running and every `IDLE_REFRESH_MS` (30 s) otherwise, so a schedule that fires while the page is open shows up; the refresh pauses while a change is being saved (an older refresh can never put the old state back), a failed one is tried again, and everything is cancelled on unmount |
| `ScheduleList.tsx`, `ScheduleCard.tsx` | Each schedule as a card — its pipeline (a link to the builder), the timing in words, an on/off `ToggleSwitch`, "Next run" (or "Off. It will not run until you turn it on."), "Last run" (the date and a status badge, a link to the run), why the last time could not start, and Run now / Edit / Delete — or, while being edited, as its form with the pipeline's inputs, across the whole row. Delete asks first, with focus on "Keep it", which gives focus back to Delete; closing the form returns focus to Edit. "Run now" opens the run it started |
| `paths.ts` | `SCHEDULES_PATH`, the one place the route is written, and `OLD_SCHEDULES_PATH` (`/runs/schedules`), which redirects to it |

### `features/settings`

- `useLLMSettings()` loads `GET /api/llm-settings`, holds the form (active
  provider, a typed key and a model per provider) and saves it. `toUpdate()`
  sends only providers whose model changed or whose key was typed, so an
  untouched provider keeps following the server default. A typed key is cleared
  from the form once saved; the API never sends a key back.
- `SettingsPage` shows one tab at a time, by its address (`TABS`: the slug,
  the label and the section, a registry rather than a branch per tab): its
  header, the tab row, the tab's section and the legal links.
  `ProvidersSection` (Settings → Providers, at `/settings`) renders the provider
  picker and one `ProviderCard` (key status, password field, "Remove saved
  key", default-model select) each.
- `MemorySection` (Settings → Memory), through `useMemory()` (`GET /api/memory`, the
  draft, `dirty`, `save`): what AIMIx keeps in mind in every chat, plan and run, as one
  text the person writes like a brief to a new colleague, with the characters used of
  the server's `max_chars` and when it was last saved; "Save memory" is enabled once the
  text differs from what is saved and fits, and the outcome is a `NoticeLine`.
- `UsageSection` (Settings → Usage) shows the last `USAGE_DAYS` (30) days from
  `useUsage()` (`GET /api/usage`, cancelled on unmount): runs, cost (with the
  token split in its tooltip) and tokens, then a list of pipelines with their
  runs, tokens and cost, costliest first (a deleted pipeline is marked). It says
  so when there were no runs, and that the real cost is higher when some model
  has no known cost. A load failure is an alert; the section never blocks the
  rest of the page.
- `EmailBlock` (Settings → Account, first): the address reset links and
  notifications go to, from `useAccount().details` (`GET /api/account` on mount,
  aborted on unmount): save a new one or remove it with the password asked again
  (`PUT /api/account/email`), and the "Email me when a run ends, waits for me, or a
  schedule cannot start" switch (`PUT /api/account/notifications`), off until there
  is an address. `AccountFields.tsx` holds the `Block`, `PasswordField`, `FIELD` and
  `Outcome` the Account blocks share; `core/auth/passwordRule.ts` the rule shown
  under a new password here and on the reset page.
- `AccountSection` (Settings → Account), through `useAccount()`: change the
  password (current, new, and the new one again; "Your other devices were
  signed out"), "Download my data" (`GET /api/account/export`, saved as
  `aimix-account-<date>.json`), and "Delete my account", which asks for the
  password and a checked "I understand that this cannot be undone", then goes
  to `/`. Each action has its own `useSubmission`. The page's tests render it
  signed in, on its route, through `testRender.tsx` (`renderSettingsPage(path)`).
- `useSubmission()` is the busy flag, notice and `submit(task, done, failed)`
  every section shares; `NoticeLine` shows the notice (`status`, or `alert` for
  an error).

Integrations (the user's own MCP servers):

| File | Role |
|---|---|
| `IntegrationsSection.tsx` | Heading, a plain-words explanation, the list, "+ Add an integration" and the section's notice |
| `IntegrationCard.tsx` | One server: name, host, an on/off `ToggleSwitch`, an "Ask me before its tools act" switch (on by default; says in words that chat cannot use the tools of an integration that asks), header names, the number of tools once tested, "Test connection", Edit, and Delete with an inline `ConfirmAction` that takes focus ("Keep it") and gives it back |
| `ConnectionTestResult.tsx` | An always-present `aria-live` region: "Connecting…", the tools found (name and description), or why the test failed |
| `IntegrationForm.tsx`, `HeaderRows.tsx` | Add or edit: name (typed as snake_case), server URL, and header rows whose values are password fields; a saved value shows only as "Saved value ending in …", and is kept when its field is left empty |
| `integrationDraft.ts` | Pure helpers: the form draft, `draftProblem` (mirrors the backend rules: name pattern, URL, header names and values; every value again when the address changes), `toCreate`, `toPatch` (only what changed; a kept header is sent without its value) |
| `useIntegrations.ts` | Loads the list, creates, updates, switches on/off (`setEnabled`, and `setRequireApproval` for "Ask me before its tools act") and deletes through `useSubmission`, and keeps each connection test's result while the page is open (tests still running are cancelled on unmount) |
| `actionButton.ts` | The small secondary button styles the section uses (the page keeps one `GlowButton`) |

Webhooks (set up by chat; this tab shows and changes them):

| File | Role |
|---|---|
| `WebhooksSection.tsx` | Heading, a plain-words explanation, the two lists ("Start a workflow from another app", "Send results to another app") with what to ask the chat while one is empty, and the section's notice |
| `WebhookItem.tsx` | One webhook: the workflow, its last call, an on/off switch, "Show link" (the chat's `WebhookCard`, which reads the link only then), "New link" and Delete, each asked first through `ConfirmAction.tsx` (`QUESTIONS`, one entry per action; the Integrations card uses it too); a renewed link is read again |
| `DeliveryItem.tsx` | One delivery: the workflow, the service with the address's host and last characters, where sending stands, Confirm while it waits for the OK (then an on/off switch), and Remove |
| `useWebhooks.ts` | Loads both lists together, then switches, renews and deletes webhooks and confirms, switches and removes deliveries through `useSubmission` |

### `features/landing`

The public front page at `/`, structured after a product-marketing page: hero,
"Built on" marquee, what it is, platform, how it works, use cases, tools,
security, FAQ, closing call to action and footer. It keeps the app's palette
(sky → indigo → purple on `#050816`) and only claims what the product does.
This version is closed source, so the page carries no licence, repository link
or install instructions and links nowhere off-site; `LandingPage.test.tsx`
fails if such text or an external link appears. `RELEASE_STAGE` in
`content/site.ts` ("Beta") labels the release in the nav and footer — change that
one word to say "Demo" — and is kept out of the hero on purpose.

| File | Role |
|---|---|
| `LandingPage.tsx` | Composes the sections; the only place that knows their order |
| `content/site.ts`, `product.ts`, `solutions.ts` | All copy as typed data: nav and footer links, hero steps, stats, features, process, use cases, tools, security points, FAQ. Edit text here, not in JSX |
| `LandingSection.tsx` | One section: anchor, labelled region, centred heading block revealed on scroll |
| `useLandingCtas.ts` | The two calls to action, switched once on `useAuth()` ("Get started" / "Sign in", or "Open the app" for a signed-in visitor) |
| `Hero.tsx`, `HeroScene.tsx`, `HeroSteps.tsx` | The headline, the 3D backdrop, and the four-step tabs over a product window |
| `ConstellationFallback.tsx` | The same pipeline drawn as flat SVG: shown while three.js loads and when there is no WebGL or reduced motion is on |
| `SceneBoundary.tsx` | Error boundary: if the 3D scene throws, the flat version stays |
| `scene/` | The react-three-fiber constellation. `sceneLayout.ts` (pure, shared with the SVG), `Nodes`, `Edges` (travelling pulses), `Backdrop` (stars, rings), `PipelineScene.tsx` (the lazy default export) |
| `StackedSwap.tsx` | Cross-fades states stacked in one grid cell, so switching never shifts the layout |
| `useStepCarousel.ts` | Auto-advance for the hero tabs; stops on a manual choice, pauses on hover/focus |
| `PerspectiveWindow.tsx`, `previewPanels.tsx` | The product window that settles flat as it scrolls into view, and its four mock screens |
| `ProcessSection.tsx`, `PlatformSection.tsx`, … | The remaining sections, one component each |

How the 3D hero degrades: `HeroScene` renders WebGL only when `hasWebGL()` is
true and the visitor has not asked for reduced motion; the three.js chunk is
loaded lazily (`PipelineScene` is a `React.lazy` default export, so `three` never
enters the main bundle). It stops rendering while off-screen (`useInView`).
Pixel ratio is capped at 1.5. The scene reads the pointer from `window`, not the
canvas, because the headline sits on top of it.

### `features/auth`

`LoginPage` and `RegisterPage` share the `AuthCard` (glass `SpotlightCard`,
`BlurText` title, `GlowButton` submit) inside `AuthLayout` (full-screen
`Aurora` plus the hero with `RotatingText`) and call `useAuth()`. A successful sign-in
goes to `HOME_PATH`, the mission workspace. The card ends with `LegalLinks`; its
`notice` prop puts a line above the button, which `RegisterPage` uses to name the
terms of use and the privacy policy before the account is created. `RegisterPage`
also takes an optional email address. `LoginPage` links to `/forgot-password`
(`ForgotPasswordPage`: the address, then a status line saying an email may be on
its way, whatever the server knows; a 503 says the server cannot send email), and
a reset link opens `/reset-password?token=…` (`ResetPasswordPage`: a new password
twice, sent with the token; done, it offers to sign in; without a token it says
the link is incomplete and where to ask for one). The `AuthCard`'s `submitLabel`
is optional, for a card that is only read.

### `features/legal`

The three public legal pages, in French: `LegalPage` picks the document by path
and renders it through `renderMarkdown`, with a "Version provisoire" note while
an operator fact is missing. `operator.ts` holds those facts (`null` shows as a
visible "[à compléter : …]" marker), `documents/` the Markdown texts with
`{{fact}}` placeholders, `fillFacts.ts` the substitution (an unknown placeholder
throws). What to fill in and what keeps the texts true: [legal.md](legal.md).


# Frontend reference

React 19 + TypeScript (strict) + Vite 7, React Router 7, Tailwind CSS 4,
`motion` for animation, `three` + `@react-three/fiber` for the landing page's 3D
hero, `lucide-react` icons, `marked` + `DOMPurify` for Markdown, Vitest +
Testing Library for tests.

```
frontend/src/
  main.tsx          # StrictMode → BrowserRouter → AuthProvider → MotionConfig → App
  App.tsx           # route table, AppNav, AppShell
  styles.css        # Tailwind import + what utilities can't express
  core/             # cross-feature, the only layer that talks to the backend
    api/            # client.ts, endpoints.ts, types.ts, one module per resource
    auth/           # tokenStorage.ts, AuthContext.tsx, RequireAuth.tsx
    hooks/          # useModels.ts, useAgentTools.ts, useCancellableRequest.ts, useLatest.ts, useNow.ts
    markdown/       # renderMarkdown.ts
    time.ts         # elapsedMs, formatDuration, formatDateTime
    ui/             # shared presentational components and motion (no data access)
      reactbits/    # effects adapted from React Bits, with its LICENSE.md
  features/
    auth/           # LoginPage, RegisterPage, AuthCard, AuthLayout
    landing/        # the public front page at /: sections, content/, scene/ (3D hero)
    chat/           # ChatPage, ChatMessages, ChatComposer, useChatStream
    files/          # FilesPage, UploadPanel, FileRow, useFiles, fileFormat, saveBlob
    pipelines/      # PipelineBuilderPage, AutoPipelinePage, hooks, subcomponents
    runs/           # RunsPage, LiveRun, useRun and the run history
    schedules/      # the Schedule panel (builder) and the Schedules view of the Runs screen
    settings/       # SettingsPage: LLM providers and Integrations (users' MCP servers)
    templates/      # TemplatesPage (the mission template gallery), useTemplates, cards
```

## Routing (`App.tsx`)

| Path | Page | Auth |
|---|---|---|
| `/` | `LandingPage` (lazy-loaded) | public |
| `/login` | `LoginPage` | public |
| `/register` | `RegisterPage` | public |
| `/chat` | `ChatPage` | guarded |
| `/pipeline` | `PipelineBuilderPage` | guarded |
| `/auto-pipeline` | `AutoPipelinePage` | guarded |
| `/templates` | `TemplatesPage` | guarded |
| `/files` | `FilesPage` | guarded |
| `/runs`, `/runs/:runId` | `RunsPage` (one route, `/runs/:runId?`) | guarded |
| `/runs/schedules` | `SchedulesPage` (a fixed path, so it wins over `:runId`; `SCHEDULES_PATH`) | guarded |
| `/settings` | `SettingsPage` | guarded |
| `*` | redirect to `/login` | — |

Guarded routes render inside `AppShell`: a static `AmbientBackdrop`, the fixed
top nav (its highlight slides between items; "Pipelines" covers the pipeline
screens, the template gallery and the run history, including the routes below
them such as `/runs/7` and `/runs/schedules`) and the `RequireAuth` outlet, which `PageTransition`
eases in when the first path segment changes (so `/runs` → `/runs/7` keeps the
page mounted). The nav holds Chat, Pipelines, Files and Settings. Below the `sm`
breakpoint its items are tighter and "Log out" is an icon (still named "Log out"),
so the bar fits a 390px phone; add an item only after checking that width.
`RequireAuth` checks `hasSession()` from storage directly, so a page reload
resolves the session before the first render without a redirect flash.

## `core/api/` — the gateway

| File | Contents |
|---|---|
| `endpoints.ts` | `API` object: **every** `/api/...` path. No other file may contain one. |
| `types.ts` | Payload interfaces: auth, pipelines, agent tools, run results with tool call metadata, runs (`Run`, `RunStep` — a `StepResult` plus status, error and times — `RunSummary` with its `RunTrigger` and `schedule_id`, `RunPage`, `RunStatus`, `RunStepStatus`) and schedules (`Schedule`, `ScheduleTiming`, `ScheduleFrequency`, `ScheduleInput`, `SchedulePatch`, `SchedulePreview`). |
| `client.ts` | `request<T>()` for JSON, `requestBlob()` for downloads and `streamText()` for streaming; `ApiError`. `request` and `requestBlob` share one send-with-refresh path. |
| `files.ts` | `listFiles`, `uploadFile` (one file, `replace` to overwrite), `downloadFile` (a `Blob`, fetched with the bearer header — never a token in a URL) and `deleteFile` |
| `auth.ts` | `login`, `register` |
| `chat.ts` | `streamChatReply` |
| `models.ts` | `fetchModels` |
| `agentTools.ts` | `fetchAgentTools` for the current pipeline tool catalogue |
| `pipelines.ts` | `listPipelines`, `savePipeline`, `runPipeline` (the synchronous compatibility call; the screens start runs with `runs.ts`), `generatePipeline` and `revisePipeline` (1 h, `GENERATION_TIMEOUT_MS`; the latter takes an abort signal) |
| `templates.ts` | `listTemplates` and `createFromTemplate` (the caller's own pipeline from a template), both cancellable with a signal |
| `llmSettings.ts` | `fetchLLMSettings`, `saveLLMSettings`, `removeProviderKey` |
| `integrations.ts` | `listIntegrations`, `createIntegration`, `updateIntegration` (`PATCH`), `deleteIntegration`, and `testIntegration` (cancellable, `CONNECTION_TEST_TIMEOUT_MS` = 60 s, above the backend's 30 s `MCP_TIMEOUT_SECONDS`) |
| `documents.ts` | `extractDocument` (10 min, `UPLOAD_TIMEOUT_MS`, above the worst case for OCR of a long scan) and `DOCUMENT_FORMATS`, the one list of document kinds and extensions (mirroring the backend's `READERS`), with `DOCUMENT_ACCEPT` for a file input and `DOCUMENT_KINDS` for copy, landing page included |
| `runs.ts` | `startRun`, `listRuns` (page, optional pipeline), `getRun`, `cancelRun`, `resumeRun`, `deleteRun` — all with the default 30 s timeout, since a run executes on the server |
| `schedules.ts` | `listSchedules` (all, or one pipeline's), `createSchedule`, `updateSchedule` (`PATCH`), `deleteSchedule`, `runScheduleNow` and `previewSchedule` (when a timing would first run) — each takes an optional abort signal, all with the default 30 s timeout |
| `errorMessage.ts` | `errorMessage(cause, fallback)`: a caught value as words for the person (an `ApiError`'s message, else the fallback) |

### What `client.ts` does for every call

- Adds `Authorization: Bearer <access>` when a token exists.
- Sets `Content-Type: application/json` when there is a body.
- Enforces a timeout with `AbortSignal.timeout` — 30 s by default, one hour
  (`GENERATION_TIMEOUT_MS`) for chat streams, or a per-call `timeoutMs`.
- On a non-2xx response, parses `{error, detail}` into
  `ApiError(message=detail, status, code=error)`; a non-API body (e.g. a proxy
  page) degrades to `"Request failed (<status>)"`.
- On **401**, clears the stored tokens so the route guard sends the user to
  `/login`.
- Network failure → `ApiError` with `code: 'network_error'`, status 0;
  timeout → `code: 'timeout'`.

Branch on `error.code`, never on `error.message`.

## `core/auth/`

| File | Role |
|---|---|
| `tokenStorage.ts` | The **only** module that touches `localStorage` (`access_token`, `refresh_token`). Every access is wrapped in try/catch. |
| `AuthContext.tsx` | `AuthProvider` + `useAuth()` → `{ isAuthenticated, login, register, logout }`. |
| `RequireAuth.tsx` | Route guard; redirects to `/login` with `state.from`. |

## `core/hooks/useModels.ts`

Loads `GET /api/models` once and returns `{ models, defaultModel, error }`.
Both pipeline screens use it; the frontend never hard-codes a model list.

## `core/hooks/useAgentTools.ts`

Loads `GET /api/agent-tools` for the builder's tool picker. The catalogue
contains exact names, descriptions, and sources (`AIMIx`, `MCP`, or the name of
one of the user's integrations); pipeline steps store names rather than copying
tool definitions.

## `core/hooks/useCancellableRequest.ts` and `useLatest.ts`

`useCancellableRequest()` → `{ start, cancel, finish }` keeps at most one request
in flight: `start()` aborts the previous one and returns a fresh
`AbortController` whose signal goes to the `core/api` call, `cancel()` aborts the
current one, and leaving the screen aborts it too. `finish(controller)` is true
only for the request still current, so a superseded or unmounted one never
updates state. `useLatest(value)` is a ref that always holds the latest value,
for async work that must read it when it finishes. `useAttachDocument` and
`useRevisePipeline` use both.

## `core/hooks/useNow.ts` and `core/time.ts`

`useNow(ticking)` returns the current time, refreshed every second
(`CLOCK_TICK_MS`) while `ticking`, for live elapsed times. `time.ts` holds the
pure helpers screens share: `elapsedMs(startedAt, finishedAt, now)`,
`formatDuration(ms)` ("4.2 s", "3 min 05 s") and `formatDateTime(iso)`.

## `core/markdown/renderMarkdown.ts`

`marked` → HTML → `DOMPurify.sanitize`. Model output is untrusted, so any
`dangerouslySetInnerHTML` must go through this function.

## `core/ui/` — shared presentation and motion

Components here render and animate; they never fetch or touch storage.

| File | Role |
|---|---|
| `brand.ts` | `BRAND_COLORS` (the logo's sky → indigo → purple) for WebGL, canvas and inline gradients |
| `BrandMark.tsx` | The animated "AIMIx" wordmark used by every header |
| `GlowButton.tsx` | Primary call to action: brand gradient, StarBorder while usable, ClickSpark, `busy` spinner. One per view. Also exports `glowButtonClass` / `BUTTON_SIZES` (sm, md, lg), the single source for the button look |
| `GlowLink.tsx` | `GlowButton`'s look on a router `Link`, for navigation that should stay a real link |
| `TiltCard.tsx` | Leans its children toward the pointer in 3D; flat on touch and under reduced motion |
| `webgl.ts` | `hasWebGL()`: probes for a context and releases it, so effects can pick a fallback |
| `ActivePill.tsx` | Selected-item highlight shared through a motion `layoutId`, so it glides between nav items, tabs and pickers. In a group that moves while it stays on screen (the run tabs under a live status bar), give each item's pill its own `layoutDependency` (its key): it then glides only when the selection changes |
| `PageTransition.tsx` | Enter-only fade/slide keyed by the route |
| `AmbientBackdrop.tsx` | Fixed, static glow behind the signed-in screens |
| `BusyNotice.tsx`, `Spinner.tsx` | Loading line with shimmer text; the spinner (`decorative` hides it inside a labelled control) |
| `ToggleSwitch.tsx` | An on/off `role="switch"` with its state in words ("On" / "Off") beside it: `checked`, `label` (its accessible name), `disabled`, `onChange(next)`. Shared by the integrations and the schedules |

`core/ui/reactbits/` holds components adapted from [React Bits](https://reactbits.dev)
(MIT + Commons Clause — keep `LICENSE.md` next to them): `Aurora` (WebGL2
background, split into `aurora/` shader, palette, program and renderer
modules), `GradientText`, `ShinyText`, `BlurText`, `RotatingText`,
`SpotlightCard`, `StarBorder`, `ClickSpark`, `CountUp`, `AnimatedContent`
(on mount, or once on first scroll into view with `whenInView`).
They are trimmed to the props the app uses and refactored to the size
budgets; take a new one from the site the same way rather than pasting it.

Rules for motion:

- `MotionConfig reducedMotion="user"` (in `main.tsx`) makes every motion
  animation honour the OS setting; CSS effects use `motion-safe:` utilities and
  `Aurora` renders a single still frame.
- Effects are decorative: `Aurora` and `ClickSpark` render nothing when WebGL2
  or a 2D canvas is missing, and animated text keeps a plain `sr-only` copy
  (as a sibling, never inside the styled element) for assistive tech.
- Do not use `bg-clip-text` on a parent of transformed letters — Chrome clips to
  their untransformed positions. `RotatingText` takes `colors` instead.
- Keep `backdrop-blur` off panels that sit over an animated background; the
  blur is recomputed every frame.
- Scroll-triggered motion (`whileInView`, `useInView`, `useScroll`) needs
  `IntersectionObserver` / `ResizeObserver`, which jsdom lacks; `test-setup.ts`
  installs inert stand-ins, so such content mounts but never "scrolls into view"
  in tests.
- Anything that starts a reveal from outside the viewport (e.g. sliding in from
  the side) must sit inside an `overflow-x-clip` ancestor, or a phone widens the
  page before the reveal fires.
- Auto-advancing or looping content (the hero's tab carousel, the tech marquee)
  pauses on hover/focus, stops once the visitor takes over, and does not run
  under reduced motion. The 3D hero backdrop deliberately has no on-screen pause
  control; it is decorative, honours reduced motion and stops rendering while
  off-screen. Add a control back if WCAG 2.2.2 conformance is required.

## Features

### `features/chat`

- `useChatStream()` owns the transcript (`messages`), `isLoading`, and `send()`.
  `send` appends the user message and an empty AI message, then appends chunks
  as they stream. An `AbortController` in a ref cancels the stream on unmount.
- `ChatPage` renders the header, a soft `Aurora`, the transcript and the
  `ChatComposer`. `ChatMessages` animates each bubble in (AI messages via
  `renderMarkdown`); an AI reply is drawn once its first token arrives, with
  the typing dots in its place until then. A fresh conversation offers starter
  prompts that fill the composer.

### `features/pipelines`

| File | Role |
|---|---|
| `PipelineBuilderPage.tsx` | Builder screen: saved list, name, run inputs, steps, run form, diagram + results; under its title the foldable "Ask AIMIx to change this pipeline" and "Schedule this pipeline" ([`features/schedules`](#featuresschedules)) panels. It follows the open pipeline's newest run (`features/runs/useFollowedRun`): the diagram shows that run's live step statuses when the run executed exactly the version on screen, and its status bar (`FollowedRunBar`: Stop, Resume, Open in Runs) sits under the run form. Leaving the page does not stop a run; reopening the pipeline shows it again |
| `AttachDocument.tsx`, `useAttachDocument.ts` | "Attach a document" under every run input: choose a PDF, Word, Excel, PowerPoint, image, HTML, CSV or text file (the picker's `accept` and the helper text both come from `DOCUMENT_FORMATS`), the server reads it (`core/api/documents.ts`), and its text is added to the input under a `[Document: name]` line, where it stays editable. The hook reads its callback when the file *finishes* (so text typed meanwhile is kept), replaces a file still being read, and cancels on unmount. Refusals show the backend's reason under that field |
| `RecentPipelines.tsx`, `RunInputCard.tsx` | The builder's saved-pipeline list and its "Run Execution" panel: one labelled field per named input (all required), or a single free-text field when the pipeline declares none. `RunInputCard` exports `RunInputFields` (those fields alone, with "Attach a document"), which the schedule form asks its inputs with too |
| `FoldablePanel.tsx` | `PanelToggle` (the bar: a heading holding one button with an icon, a title and a chevron, `aria-expanded` / `aria-controls`) and `Foldable` (the body, animated by its grid row, `inert` while folded). `RevisePanel` and `SchedulePanel` are built on them |
| `usePipelineBuilder.ts` | State + transport: pipeline, saved list, dirty state, and actions for editing steps and inputs, adding parallel or following stages, replacing the whole draft (`replace`, for an accepted revision), saving and starting a run (`run` returns the started run for the page to follow). A changed pipeline must be saved before running. |
| `AutoPipelinePage.tsx` | Describe → generate → preview diagram → refine it in a sentence → edit inputs and steps → save |
| `useAutoPipeline.ts` | Generation, editing (including the planned inputs), adding or removing output steps, `replace` (an accepted revision) and saving the proposed workflow (later saves update it) |
| `RevisePanel.tsx` | "Ask AIMIx to change this pipeline": a foldable panel (open by default on the auto page) with the change box, clickable example instructions, a busy line with Stop, and the review. Ctrl/⌘ + Enter asks. Apply hands the revision to `onApply` (the page replaces its draft and leaves it unsaved); it never saves. Props: `pipeline`, `onApply`, optional `plannerModel`, `disabled`, `defaultOpen`, `headingLevel`. Mounted under the builder's title and under the auto page's diagram |
| `RevisionReview.tsx` | A proposal: the change list in plain words (added / changed / removed marks), a `PipelineGraph` preview, Apply and Discard; "Nothing to change" when the planner changed nothing |
| `useRevisePipeline.ts` | `useRevisePipeline(pipeline)` → `{ proposal, stale, busy, error, propose, cancel, discard }` over `POST /api/pipelines/revise`. The proposal keeps the draft's id (so a save updates it) and only applies to the draft it was made from: an edit sets it aside (`stale`), and an answer for a draft edited meanwhile is dropped. Aborts on unmount and on `cancel` |
| `useRevisePanel.ts` | The panel's own state over `useRevisePipeline` (typed instruction, applied flag, `edit` / `pick` / `ask` / `apply` / `discard`) and `panelStatus`, the text of its live status line |
| `revision.ts` | `describeChange` (a change as a sentence), `adoptRevision`, the example instructions and the instruction length limit (mirrors the backend's) |
| `buttonStyles.ts` | Primary and secondary in-card button looks for actions beside a page's GlowButton |
| `PipelineInputsEditor.tsx` | The named run inputs (name, label, description), shared by both screens; names are typed as snake_case and problems show before saving |
| `pipelineInputs.ts` | Pure helpers for named inputs and attached documents (`appendDocument`, `documentSummary`): the naming rule (mirrors the backend), `{placeholder}` checks, the run form's `RunDraft`, and `runRequest`, which sends only declared inputs |
| `StepEditor.tsx` | Builder sidebar: each step's stage, title, expected output, agent role, tool access, model and prompt |
| `PromptPlaceholders.tsx` | Under a prompt: `{input}` and the declared `{name}` placeholders, plus a warning for a placeholder nothing fills |
| `StepAgentFields.tsx` | Agent role and tool policy controls shared by manual and generated step editors (`null` all, `[]` none, selected names otherwise); the checklist groups tools by source, so an integration's tools sit under its name |
| `StepRoleFields.tsx` | A step's title, its Intermediate / Output toggle and its expected output, shared by both editors |
| `GeneratedSteps.tsx` | Generated steps drawn stage by stage; parallel steps side by side |
| `PipelineGraph.tsx`, `GraphNodeCard.tsx` | Flow diagram Input → stages → Outputs with fork/merge brackets, a legend and controls to add parallel steps or a following stage; the Input terminal lists the named inputs; nodes show title, model, status, an Output badge and, before a run, their expected output; clicking a finished (or failed) node opens its output (or error). Stages slide in; during a run connectors pulse and running nodes carry a StarBorder. `NODE_STATUS_STYLES` holds each status's colours and word: Not run, Waiting, Running, Done, Failed, Stopped |
| `pipelineGraph.ts` | Pure model behind the diagram (`buildGraph`, which takes a followed run's steps for live statuses; `liveNodeStatus`) and the `OutputTarget` type |
| `PipelineRunView.tsx` | Diagram + "Outputs" / "All steps" tabs + run stats (outputs, steps, stages, seconds — counted up once the run has ended, with a one-line `sr-only` summary); deliverables are grouped by stage. Given a followed run's `liveSteps` (and its `runKey`), nodes show each step's status, outputs appear as soon as they are saved, and "All steps" lists every step — a run in progress opens on it, a finished one on its outputs |
| `StepProgressCard.tsx` | In "All steps", a step without an output: its status, live elapsed time and, for a failed step, the error |
| `StepHeading.tsx` | Title row of a step's output card (name, model, Output badge) |
| `RunResults.tsx`, `ToolCallTrace.tsx` | Every step's output grouped by stage, with called tool names and success/error statuses |
| `OutputCard.tsx` | One output: rendered/raw toggle, copy, the input it saw, folding for long text |
| `useCopyToClipboard.ts` | Clipboard copy with short "Copied" feedback |
| `stages.ts` | `groupByStage`, `nextStage`, `outputOrders` (preview of which steps are outputs; mirrors the backend rule) and `stepLabel` |
| `StageInput.tsx`, `StageHeader.tsx`, `StageArrow.tsx` | Stage picker, stage label ("N steps in parallel"), connector |
| `PipelineNav.tsx` | Switch between Pipeline, Auto Pipeline, Templates and Runs |
| `modelLabel.ts` | Human-friendly label for a model id |

### `features/templates`

The template gallery at `/templates`, reached from the Templates tab of
`PipelineNav` and the "Start from a template" link on Auto Pipeline. Using a
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
| `UploadPanel.tsx` | Drop zone plus a "Choose files" `GlowButton` that opens a hidden multi-file input (`accept` from the server's `allowed_extensions`), the accepted types in plain words and the size cap, and each refused file with its reason; a taken name offers "Replace". A window-level guard keeps a file dropped beside the zone from replacing the page |
| `FileRow.tsx` | One file: type icon (lucide), name, folder, size, date, download and delete buttons with a spinner while busy; delete asks first (focus starts on Cancel, Escape cancels) and errors show under the row |
| `useFiles.ts` | State + transport: loads the listing, uploads one file per request (so each refusal is reported against its file), replace/dismiss, download (then `saveBlob`) and delete (a 404 counts as deleted). One `AbortController` per mount cancels everything on unmount |
| `fileFormat.ts` | Pure helpers: `formatBytes` (decimal units like the server's limits), `formatDate`, `fileName`, `folderOf`, `fileIcon`, `describeTypes`, and `withFile` / `withoutFile`, which keep `used_bytes` equal to the sum of the sizes |
| `saveBlob.ts` | Hands a downloaded `Blob` to the browser as a file save through an object URL |

### `features/runs`

Runs execute on the server; the screens follow them by polling. `features/runs`
builds on the diagram pieces of `features/pipelines` (`PipelineRunView`,
`OutputCard`, `RunResults`), and the builder embeds its header and hooks.

| File | Role |
|---|---|
| `useRun.ts` | `useRun(runId)` → `{ run, error, busy, stop, resume, adopt }`. Fetches the run, polls it every `RUN_POLL_INTERVAL_MS` (1.5 s) while it is queued or running and stops once it ends; unmounting or switching runs clears the timer and aborts the request in flight. A resumed run is polled again; `adopt(run)` shows a run already in hand (one just started) at once. A failed poll is retried, a 404 is not |
| `useLatestRun.ts` | The builder's follower: loads the pipeline's newest run when it opens (`GET /runs?pipeline_id=…&limit=1`) and `follow(run)` switches to a run started here |
| `useFollowedRun.ts`, `FollowedRunBar.tsx` | What the builder needs from that run: whether one is active, the run the diagram may show (`shown`, only a run of exactly the version on screen) and its duration; and its status bar with Stop, Resume and "Open in Runs" |
| `useRunHistory.ts` | The history list: pages of `RUN_PAGE_SIZE` (20), refreshed every `RUN_LIST_REFRESH_MS` (5 s) while a listed run is active; `update` keeps a line in step with the open run, `remove` deletes a run |
| `LiveRun.tsx` | **The embeddable live run**: `<LiveRun run onStop onResume busy error actions>{children}</LiveRun>` — the run's own diagram with live statuses, the status bar, any `children` (e.g. its inputs), then the results. Pair it with `useRun` |
| `LiveRunHeader.tsx` | Status bar: status badge, "2 of 5 steps done", ticking elapsed time, Stop / Resume and extra `actions`, an `aria-live` line, and why the run stopped (the failed step and its error, "You stopped this run", "The server restarted…") |
| `RunStatusBadge.tsx` | A run status as a pill; `RUN_STATUS_STYLES` holds the words (Queued, Running, Done, Failed, Stopped, Interrupted) and colours |
| `runButtons.ts` | `RUN_BUTTON`: the looks of the run controls (stop, resume, neutral, danger) |
| `runStatus.ts` | `isActive`, `isResumable` (mirroring the backend's status sets), `finishedStepCount`, and `ranThisVersion(run, pipeline)` — whether a run executed exactly the pipeline on screen |
| `RunsHeader.tsx` | The header both views of the Runs screen share: brand, the pipeline sub-navigation, and two underline tabs, History (`/runs`) and Schedules (`/runs/schedules`, `aria-current` on the one shown), then a line of text. The sub-navigation is unchanged, so it still fits a phone |
| `RunTriggerTag.tsx` | A small clock and "Scheduled" for a run a schedule started (`trigger === 'schedule'`); nothing for any other run. Shown beside the date in `RunHistoryList` and in `RunDetail`'s header |
| `RunsPage.tsx`, `RunHistoryList.tsx`, `RunDetail.tsx`, `DeleteRunButton.tsx` | The Runs screen: the list (pipeline, status, start, duration) beside the open run on wide screens, one at a time on a phone (with "← All runs"); the detail shows the run's inputs and the live run; Delete asks "Delete this run for good?" with Keep focused, and is offered only once the run has ended |

### `features/schedules`

Runs that start on their own (`/api/schedules`). Two screens use one form:
the builder's **Schedule this pipeline** panel creates a schedule, and the
**Schedules** view of the Runs screen (`/runs/schedules`) lists, switches, edits,
runs and deletes them.

| File | Role |
|---|---|
| `scheduleDraft.ts` | Pure helpers: `ScheduleDraft` (what the form holds), `FREQUENCIES` (one rule per preset — its label, which fields it asks for, how it reads in words: Strategy + Registry, mirroring the backend's presets), `describeTiming` ("Every Monday at 09:00, Paris time"; hourly names no zone; a day past the 28th adds "or the last day, in shorter months"), `formatNextRun` ("Mon 26 Oct, 09:00" on the schedule's own clock), `timeZoneOptions` (UTC first, then every zone `Intl` knows, and the current one), `withFrequency` (hourly asks for minutes instead of a time), `scheduleProblem`, and `toCreate` / `toPatch` / `draftFromSchedule`. It works out no time itself: when a schedule runs is the server's rule |
| `ScheduleFields.tsx` | The timing fields: Repeat, Day of the week (weekly) or Day of the month (monthly), Time (or Minutes past the hour when hourly) and Time zone. Native `time` and `select` controls with `color-scheme: dark`; every control labelled |
| `ScheduleForm.tsx` | The form both screens share: the fields, a live `role="status"` summary (the timing in words, then "Next run: …"), the run inputs asked like a manual run's (`RunInputFields`, under a "What each run is given" legend), a problem shown as an alert only after a first try, and an optional `blocked` reason that disables saving. It keeps its own draft, starting from `initial`; give it a `key` to start over |
| `useSchedulePreview.ts` | `useSchedulePreview(timing \| null)` → `{ nextRunAt, error, loading }`: asks `POST /api/schedules/preview` once the timing has stayed put for `PREVIEW_DELAY_MS` (300 ms), aborts a request a newer timing makes obsolete or the screen leaving, ignores an answer that arrives after its request was dropped, and asks nothing for an incomplete timing |
| `SchedulePanel.tsx`, `useCreateSchedule.ts` | The builder's foldable panel (built on `FoldablePanel`, mounted under `RevisePanel`). Its body is built when first opened (a page that never opens it asks the server nothing) and starts afresh for another pipeline. An unsaved pipeline is told to save first; unsaved edits disable saving ("a schedule runs the saved version"). `useCreateSchedule(pipelineId, inputs)` → `{ busy, error, created, create }`: after a schedule is created the form is replaced by a fresh one, so one press never saves it twice, and leaving drops the request |
| `SchedulesPage.tsx`, `useSchedules.ts` | The Schedules view: loading, an empty state that points to the builder, and the list; each outcome appears as a notice. `useSchedules()` → `{ schedules, status, notice, actions }` with `update`, `setEnabled`, `remove` and `runNow` (which resolves to the started run, or `null`), over the settings' `useSubmission` (one busy flag, one notice); cancelled on unmount |
| `ScheduleList.tsx`, `ScheduleCard.tsx` | Each schedule as a card — its pipeline (a link to the builder), the timing in words, an on/off `ToggleSwitch`, "Next run" (or "Off. It will not run until you turn it on."), "Last run" (the date and a status badge, a link to the run), why the last time could not start, and Run now / Edit / Delete — or, while being edited, as its form with the pipeline's inputs. Delete asks first, with focus on "Keep it", which gives focus back to Delete; closing the form returns focus to Edit. "Run now" opens the run it started |
| `paths.ts` | `SCHEDULES_PATH`, the one place the route is written |

### `features/settings`

- `useLLMSettings()` loads `GET /api/llm-settings`, holds the form (active
  provider, a typed key and a model per provider) and saves it. `toUpdate()`
  sends only providers whose model changed or whose key was typed, so an
  untouched provider keeps following the server default. A typed key is cleared
  from the form once saved; the API never sends a key back.
- `SettingsPage` renders the provider picker and one `ProviderCard` (key
  status, password field, "Remove saved key", default-model select) each,
  then the Integrations section.
- `useSubmission()` is the busy flag, notice and `submit(task, done, failed)`
  both sections share; `NoticeLine` shows the notice (`status`, or `alert` for
  an error).

Integrations (the user's own MCP servers):

| File | Role |
|---|---|
| `IntegrationsSection.tsx` | Heading, a plain-words explanation, the list, "+ Add an integration" and the section's notice |
| `IntegrationCard.tsx` | One server: name, host, an on/off `ToggleSwitch`, header names, the number of tools once tested, "Test connection", Edit, and Delete with an inline confirmation that takes focus ("Keep it") and gives it back |
| `ConnectionTestResult.tsx` | An always-present `aria-live` region: "Connecting…", the tools found (name and description), or why the test failed |
| `IntegrationForm.tsx`, `HeaderRows.tsx` | Add or edit: name (typed as snake_case), server URL, and header rows whose values are password fields; a saved value shows only as "Saved value ending in …", and is kept when its field is left empty |
| `integrationDraft.ts` | Pure helpers: the form draft, `draftProblem` (mirrors the backend rules: name pattern, URL, header names and values; every value again when the address changes), `toCreate`, `toPatch` (only what changed; a kept header is sent without its value) |
| `useIntegrations.ts` | Loads the list, creates, updates, switches on/off and deletes through `useSubmission`, and keeps each connection test's result while the page is open (tests still running are cancelled on unmount) |
| `actionButton.ts` | The small secondary button styles the section uses (the page keeps one `GlowButton`) |

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
`Aurora` plus the hero with `RotatingText`) and call `useAuth()`.

## Conventions (from AGENTS.md §8)

- No `fetch` in components; no `localStorage` outside `tokenStorage.ts`.
- Payload types only in `core/api/types.ts`.
- Every effect that starts async work cancels it (`active` flag or
  `AbortController`).
- Tailwind utilities first; Prettier: 100 cols, single quotes.

## Tests

`npm test` (Vitest, jsdom). Existing suites include `App.test.tsx`,
`core/api/client.test.ts` (auth header, error contract, 401 handling, network
error), `core/markdown/renderMarkdown.test.ts` (sanitisation),
`core/ui/GlowButton.test.tsx`, `core/ui/reactbits/reactbits.test.tsx`
(fallbacks and accessible text of the adapted effects),
`features/chat/ChatPage.test.tsx`, `core/api/files.test.ts` and
`features/files/FilesPage.test.tsx` / `fileFormat.test.ts` (listing, upload by
input and by drop, replace, refusals, download, delete with confirmation,
cancellation), and for the landing page
`features/landing/LandingPage.test.tsx` (CTAs by sign-in state, tab keyboard
behaviour, FAQ disclosure, WebGL-less fallback), `useStepCarousel.test.ts` and
`scene/sceneLayout.test.ts` (the layout is deterministic and well-formed), and
for the gallery `features/templates/` (filters, the hook, and the page: busy
state, errors, retry and opening the builder). The
revise flow is covered by `features/pipelines/RevisePanel.test.tsx` (review,
apply, discard, nothing to change, errors, Stop, Ctrl+Enter, busy page),
`useRevisePipeline.test.tsx` (stale drafts, cancellation on unmount) and
`revision.test.ts`; fixtures live in `revisionTestData.ts`. The shared request
hooks have `core/hooks/useCancellableRequest.test.tsx` and `useLatest.test.tsx`. The
Settings page has `SettingsPage.test.tsx`, `useLLMSettings.test.tsx`, and for
integrations `IntegrationsSection.test.tsx` (list, add, validation, test
connection, delete confirmation, switch, edit with hints), `useIntegrations.test.tsx`
and `integrationDraft.test.ts`; `testData.ts` holds their fixtures and `byPath`,
a fetch stand-in that answers each API path. For
runs: `core/api/runs.test.ts`, `features/runs/useRun.test.tsx` (polling with
fake timers, abort on unmount, stop, resume, adopt), `useLatestRun.test.tsx`,
`LiveRun.test.tsx` (live statuses, Stop/Resume, failure explanation) and
`RunsPage.test.tsx` (list, deep link, delete with confirmation);
`features/runs/testData.ts` builds the runs they share. For schedules:
`core/api/schedules.test.ts`, `features/schedules/scheduleDraft.test.ts` (words,
ordinals, next-run text across zones, drafts and requests),
`useSchedulePreview.test.tsx` (fake timers: the delay, the burst, the same timing
twice, a superseded request, errors, unmount), `useSchedules.test.tsx`,
`useCreateSchedule.test.tsx`, `SchedulePanel.test.tsx` (folded until opened and
asking nothing until then, the fields each frequency needs, the live summary,
every refusal, named inputs, busy, afresh per pipeline), `SchedulesPage.test.tsx`
(the list, off and failed times, toggle, delete with confirmation and focus, edit
in place, run now) and `features/runs/RunScheduledMark.test.tsx`;
`features/schedules/testData.ts` holds their fixtures and `serve`, a fetch stand-in
that answers each `METHOD /path` from a table and records the calls.
`test-setup.ts` makes `getContext` return `null`, i.e. tests run as a browser
without WebGL or canvas, and stubs the observers jsdom lacks. Watch mode:
`npm run test:watch`.

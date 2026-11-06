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
    hooks/          # useModels.ts, useAgentTools.ts, useAccountName.ts, useCancellableRequest.ts, useLatest.ts, useNow.ts, useMediaQuery.ts, useMountedRef.ts, useCopyToClipboard.ts
    markdown/       # renderMarkdown.ts, documentText.ts, RenderedMarkdown.tsx
    routes.ts       # HOME_PATH (where sign-in lands), missionPath(id), runPath(id), LEGAL_LINKS
    saveBlob.ts     # hands a downloaded Blob to the browser as a file to save
    chosenFiles.ts  # the files a file input was given, emptied so the same one counts again
    time.ts         # elapsedMs, formatDuration, formatDateTime
    usageFormat.ts  # formatCost, formatTokens, formatCount, countOf, parseCost, describeCost: counts, tokens and costs in words
    ui/             # shared presentational components and motion (no data access)
      reactbits/    # effects adapted from React Bits, with its LICENSE.md
  features/
    auth/           # LoginPage, RegisterPage, AuthCard, AuthLayout
    landing/        # the public front page at /: sections, content/, scene/ (3D hero)
    chat/           # the Chat screen over the chats the server keeps: frontend-chat.md
    files/          # FilesPage, UploadPanel, FileRow, useFiles, fileFormat
    legal/          # LegalPage: /legal, /privacy, /terms (French), operator facts
    mission/        # MissionPage: the front door, one screen from describing a mission to its results
    pipelines/      # PipelineBuilderPage, AutoPipelinePage, hooks, subcomponents
    runs/           # RunsPage, useRun, the run history, and report/: RunReport, one run as one document
    schedules/      # the Schedule panel (builder) and the Schedules screen
    settings/       # SettingsPage, one tab each: Providers, Integrations (users' MCP servers), Memory, Webhooks, Usage, Account
    templates/      # TemplatesPage (the mission template gallery), useTemplates, cards
```

## Routing (`App.tsx`)

| Path | Page | Auth |
|---|---|---|
| `/` | `LandingPage` (lazy-loaded) | public |
| `/login` | `LoginPage` | public |
| `/register` | `RegisterPage` (creates the account, signs the person in and goes to `/mission`; if only that sign-in fails it goes to `/login`) | public |
| `/legal`, `/privacy`, `/terms` | `LegalPage` (lazy-loaded; one route per entry of `LEGAL_LINKS` in `core/routes.ts`) | public |
| `/mission`, `/mission/:pipelineId` | `MissionPage` (one route, `/mission/:pipelineId?`) | guarded |
| `/chat` | `ChatPage` | guarded |
| `/pipeline` | `PipelineBuilderPage` | guarded |
| `/auto-pipeline` | `AutoPipelinePage` | guarded |
| `/templates` | `TemplatesPage` | guarded |
| `/files` | `FilesPage` | guarded |
| `/runs`, `/runs/:runId` | `RunsPage` (one route, `/runs/:runId?`) | guarded |
| `/schedules` | `SchedulesPage` (`SCHEDULES_PATH`) | guarded |
| `/runs/schedules` | redirect to `/schedules`, its old address (`OLD_SCHEDULES_PATH`; a fixed path, so it wins over `:runId`) | guarded |
| `/settings`, `/settings/:tab` | `SettingsPage` (one route, `/settings/:tab?`: Providers at `/settings`, then `integrations`, `webhooks`, `usage`, `account`; an unknown tab redirects to `/settings`) | guarded |
| `*` | redirect to `/login` | — |

Guarded routes sit behind `RequireAuth`, then inside `AppShell`: a static
`AmbientBackdrop` and `AppFrame` (the sidebar, below) around the outlet, which
`PageTransition` eases in when the first path segment changes (so `/runs` →
`/runs/7`, `/mission` → `/mission/7` and one Settings tab → another keep the page
mounted). `AppShell` is inside the guard so the sidebar's waiting-runs count is
never fetched before sign-in. `/mission` is the front door: signing in
(`LoginPage`) and "Open the app" on the landing page both go to `HOME_PATH` from
`core/routes.ts`.

**The sidebar** lists every section, from `navGroups()` in `App.tsx`: Missions and
Chat; then **Pipelines**: Builder (`/pipeline`), Auto Pipeline, Templates, Runs and
Schedules; then **Workspace**: Files and Settings. Above them the logo and the AIMIx
wordmark lead to Missions; at the foot an account card names the signed-in account
(`useAccountName`) beside Log out, and the sections scroll above it when the window
is short. Each item
owns its route and the routes below it (Runs stays lit on `/runs/7`, Missions on
`/mission/7`), and its highlight, with a bar in the brand gradient on its left edge,
slides between items. Runs carries an amber count
while runs wait for the person to approve an action (`useWaitingRuns`, polled every
5 s on every signed-in screen), with the same count in words ("Runs, 2 waiting for
you"). From `lg` up the sidebar is fixed on the left (224px) and the screens sit
beside it; below `lg` a 60px top bar holds the logo and a menu button that opens the
same sidebar as a drawer (`role="dialog"`, focus on Close, Escape or a tap outside
closes it and hands focus back; following a link closes it; the screen behind is
`inert`).

**Every standard screen** (Auto Pipeline, Templates, Runs, Schedules, Files,
Settings) uses `Page` and `PageHeader` from `core/ui/Page.tsx`: the same padding,
a `max-w-6xl` column and the screen's name (as the sidebar shows it) as its `h1`,
so titles share one left edge. Forms that read better narrow (Files, Settings, Auto
Pipeline) cap their body inside it. The full-window screens (Missions, Chat) take
`FULL_SCREEN_HEIGHT` from `core/ui/screen.ts` and scroll inside themselves; the
Builder puts its editor beside the canvas from `xl` and above it below `xl`.
`RequireAuth` checks `hasSession()` from storage directly, so a page reload
resolves the session before the first render without a redirect flash.

## `core/api/` — the gateway

| File | Contents |
|---|---|
| `endpoints.ts` | `API` object: **every** `/api/...` path. No other file may contain one. |
| `pipelineTypes.ts` | The pipeline definition, re-exported from `types.ts`: `Pipeline`, `PipelineStep`, `PipelineInput` (with its optional `default_value`), `StepCondition`, `ConditionOperator`, `StepReview`, `AgentTool`. |
| `types.ts` | Payload interfaces: auth, pipelines, agent tools, run results with tool call metadata, runs (`Run` — with `pending_approvals` —, `RunStep` — a `StepResult` plus status, error, times and its tokens and cost — `RunSummary` with its `RunTrigger` and `schedule_id`, `RunPage`, `RunStatus` including `waiting`, `RunStepStatus`, which includes `skipped`, and `RunStep`'s `rounds` and `verdict`, `RunApproval`, `ApprovalStatus`), a step's `condition` and `review` (`StepCondition`, `ConditionOperator`, `StepReview`; every `PipelineStep` has both, `null` when unset), their usage and limits (`Usage`, `RunBudget`) and the usage report (`UsageReport`, `PipelineUsage`) and schedules (`Schedule`, `ScheduleTiming`, `ScheduleFrequency`, `ScheduleInput`, `SchedulePatch`, `SchedulePreview`). |
| `authTypes.ts` | Auth payloads, re-exported from `types.ts`: `AuthTokens` and `WhoAmI` (`GET /api/protected`, with the `username`). |
| `planningTypes.ts` | Planning payloads, re-exported from `types.ts`: `GeneratedPipelineResponse`, `MissionPlanResponse` (a team, or the planner's `ClarifyingQuestion`s), `PlanAnswer`, `PipelineChange`, `RevisedPipelineResponse`. `PlanDocument` (a document as the planner reads it: name, pages, characters and an excerpt) is imported from here directly, so `types.ts` does not grow. |
| `client.ts` | `request<T>()` for JSON, `requestBlob()` for downloads and `streamText()` for streaming; `ApiError`. `request`, `requestBlob` and `streamText` share one send-with-refresh path. |
| `files.ts` | `listFiles`, `uploadFile` (one file, `replace` to overwrite), `downloadFile` (a `Blob`, fetched with the bearer header — never a token in a URL) and `deleteFile` |
| `auth.ts` | `login`, `register` |
| `chat.ts` | `streamChatReply(prompt, {chatId, timezone}, signal)`, which sends a message to a chat the server keeps and decodes the reply's NDJSON events (`chatTypes.ts`: text, tool started/finished/failed with an `action` naming what to link to, and last `usage`, what the reply used) |
| `chats.ts` | `listChats`, `createChat`, `getChat` (with its messages and their usage), `renameChat`, `deleteChat` (`chatTypes.ts`: `ChatSummary`, `ChatDetail`, `ChatSavedMessage`, `ChatSavedTool`) |
| `models.ts` | `fetchModels` |
| `agentTools.ts` | `fetchAgentTools` for the current pipeline tool catalogue |
| `pipelines.ts` | `listPipelines`, `getPipeline` (one by id, cancellable), `savePipeline`, `runPipeline` (the synchronous compatibility call; the screens start runs with `runs.ts`), `generatePipeline` (optional planner model and abort signal), `planMission` (one options object — `description`, `answers`, `mayAsk` and the optional `documents`, sent only when there are some — and an abort signal) and `revisePipeline` (1 h, `GENERATION_TIMEOUT_MS`; the latter takes an abort signal). The planning limits mirror `backend/api/schemas/planning.py`: `PLAN_DESCRIPTION_MAX_LENGTH` (20,000), `MAX_PLAN_DOCUMENTS` (5), `PLAN_DOCUMENT_EXCERPT_CHARS` (2,000) and `PLAN_DOCUMENT_NAME_MAX_LENGTH` (2,048), with `DOCUMENTS_INPUT_NAME` (`documents`), the run input every plan made with documents has. `normalizePipeline` fills what older pipelines and plans leave out (inputs, role, tools, expected output, `condition` and `review` as `null`) |
| `templates.ts` | `listTemplates` and `createFromTemplate` (the caller's own pipeline from a template), both cancellable with a signal |
| `llmSettings.ts` | `fetchLLMSettings`, `saveLLMSettings`, `removeProviderKey` |
| `memory.ts` | `fetchMemory`, `saveMemory` (Settings → Memory; `memoryTypes.ts`: `Memory`, with the server's `max_chars`) |
| `integrations.ts` | `listIntegrations`, `createIntegration`, `updateIntegration` (`PATCH`), `deleteIntegration`, and `testIntegration` (cancellable, `CONNECTION_TEST_TIMEOUT_MS` = 60 s, above the backend's 30 s `MCP_TIMEOUT_SECONDS`) |
| `documents.ts` | `extractDocument` (10 min, `UPLOAD_TIMEOUT_MS`, above the worst case for OCR of a long scan), `importDocumentFromUrl(url, signal)` (`POST /api/documents/import-url`, same timeout: the server opens a public page or file at a link and answers like `extractDocument`, `filename` being the address the link led to; `PAGE_URL_MAX_LENGTH` caps the link) and `DOCUMENT_FORMATS`, the one list of document kinds and extensions (mirroring the backend's `READERS`), with `DOCUMENT_ACCEPT` for a file input and `DOCUMENT_KINDS` for copy, landing page included |
| `runs.ts` | `startRun` (its body may carry `max_cost_usd` / `max_tokens`), `listRuns` (page, optional pipeline and status), `countWaitingRuns` (`listRuns` for `status=waiting`, one run: its `total`), `getRun`, `cancelRun`, `resumeRun` (optionally with new limits), `deleteRun` — all with the default 30 s timeout, since a run executes on the server |
| `usage.ts` | `fetchUsage(days, signal)`: what the account's runs of the last days used and cost (`GET /usage`) |
| `approvals.ts` | `approveToolCall(runId, approvalId)` and `declineToolCall(...)`: answer a tool call a run waits on; each gives back the updated run, and a clash or an expired request is a 409 `conflict` |
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
- On **401**, refreshes the session once (one refresh shared by concurrent calls)
  and retries. If the server refuses the refresh (401), or refuses the call even
  with the fresh token, the session is over: `endSession()` drops the token and
  tells `AuthProvider`, which signs the screens out, so the route guard sends the
  user to `/login`. A refresh failing for another reason (a 5xx, a 429) only drops
  the token, and the next call refreshes again. A 401 from `/login` itself is a
  wrong password, not the end of a session.
- Network failure → `ApiError` with `code: 'network_error'`, status 0;
  timeout → `code: 'timeout'`.

Branch on `error.code`, never on `error.message`.

## `core/auth/`

| File | Role |
|---|---|
| `tokenStorage.ts` | The access token, in memory only (the refresh token is an HttpOnly cookie; nothing goes to browser storage). `endSession()` drops it and notifies `subscribeToSessionEnd()` listeners (Observer): on logout, and when the server refuses the session. |
| `AuthContext.tsx` | `AuthProvider` + `useAuth()` → `{ isAuthenticated, isReady, login, register, logout, changePassword, deleteAccount }`. `changePassword` keeps this tab signed in with the new token (the server ends every other session); `deleteAccount` ends the session once the account is gone. It subscribes to the session's end and then signs out (a guarded screen goes to `/login`; a public page stays where it is, so nothing loops). Its `forgetAccountData` prop runs at each session end and on signing in; `main.tsx` passes the mission storage's `forgetAllMissions`. |
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

## `core/hooks/useAccountName.ts`

`useAccountName()` is the signed-in username from `whoAmI()` (`GET /api/protected`),
fetched once on mount for the sidebar's account card: `null` until it answers and
when it fails (the name is only shown), and unmounting aborts the request.
`App.test.tsx` stubs it, as it does `useWaitingRuns`.

## `core/hooks/useMediaQuery.ts` and `useMountedRef.ts`

`useMediaQuery(query)` is whether a CSS media query matches, kept current as the
window changes (`useSyncExternalStore`); it is `false` where the browser cannot
answer (jsdom), so tests render the narrow layout unless they stub `matchMedia`.
`useMountedRef()` is a ref that is true while the component is mounted, for the
answer of a request that cannot be cancelled (a save), which is then dropped
instead of updating state after the screen is gone.

## `core/hooks/useImagePreview.ts`

`useImagePreview(path)` fetches a picture of the user's workspace with the session
header (`core/api/files.downloadFile`: a token never goes in a URL) and returns it
as a `data:` URL, which the Content-Security-Policy's `img-src 'self' data:` lets an
`<img>` show; `null` while it loads or if it cannot. Unmounting cancels the download.
The server labels JPEG, PNG, WebP and GIF downloads with their image type.

## `core/hooks/useFileDrop.ts`

`useFileDrop(onFiles, enabled = true)` → `{ dragging, zone }` makes an element a drop
zone for files: spread `zone` on it, light it up while `dragging`, and `onFiles` gets
the files dropped (none while not `enabled`). Only drags that carry files are taken;
text keeps the browser's own behaviour. While a zone is on screen, a window-level guard
keeps a file dropped just beside it from replacing the page. The Files page's upload
panel and the Missions message box use it.

## `core/hooks/useNow.ts` and `core/time.ts`

`useNow(ticking)` returns the current time, refreshed every second
(`CLOCK_TICK_MS`) while `ticking`, for live elapsed times. `time.ts` holds the
pure helpers screens share: `elapsedMs(startedAt, finishedAt, now)`,
`formatDuration(ms)` ("4.2 s", "3 min 05 s") and `formatDateTime(iso)`.

## `core/hooks/useCopyToClipboard.ts`

`useCopyToClipboard()` → `{ status, copy, copyRich }`: `copy(text)` writes plain text;
`copyRich({ html, text })` writes both at once (one `ClipboardItem`, so a paste into a
document keeps the formatting), falling back to the plain text where rich content is
refused. `status` is `'copied'` for 1.5 s, then `'idle'`, or `'failed'` (until the next
copy) when the browser refuses both or has no clipboard. Unmounting clears the timer.

## `core/markdown/renderMarkdown.ts`

`marked` → HTML → a private `DOMPurify` instance. Model output is untrusted (a web
page or document the model read can steer it), so any `dangerouslySetInnerHTML` must
go through this function. Beyond scripts it keeps nothing that could pass for the
app's own screen: HTML only (no SVG or MathML), no form controls (`form`, `button`,
`textarea`, `select`, `label`, …), no `dialog` or `<style>`, and no `style` or `class`
attribute (the app's Tailwind classes include `fixed inset-0`), so a reply cannot draw
a fake sign-in panel or an invisible full-screen link. What Markdown makes still
renders: tables with their `align`, code blocks, lists and links. The one input
Markdown makes, a task-list box, is kept as a disabled checkbox, and any other input
becomes one. Links open in the same tab, as before, with `rel="noopener noreferrer"`.
The hooks doing this live on the module's own instance, added once.

`renderDocument(text, headingBase)` is the same sanitising for a deliverable read as a
document: the text's own top heading starts at `headingBase` (an `h1`, or the `##` of a
text that starts there, becomes `h3` under an `h2` title, so no level is skipped; never
past `h6`) and carries `data-level` for its size; each table is wrapped in a focusable,
labelled scroller (`md-table-scroll`) and each code block is focusable the same way
("Code"); number cells, with a short unit or currency code too ("3.9 s", "EUR 2.40"), get
`data-num`, so they right-align with tabular figures. It drops the model's own `data-*`
attributes, so only it can set those, except the picture path the shared hook moves to
`data-workspace-path`. `RenderedMarkdown` renders it (`prose-output prose-document`, the
reading styles in `styles.css`) and loads those pictures with `useWorkspacePictures`;
`documentText.ts` holds `plainTextOf(html)` (the plain text a copy
carries: bullets, numbers, tab-separated table rows, links as "text (address)", no Markdown
marks) and `countWords` (`Intl.Segmenter`, with a fallback).

## `core/voice/` — dictation

`MicButton` sits in every box where you ask AIMIx for work: the Missions message box
(`MissionComposer`), the Chat box (`ChatComposer`), the builder's "Ask AIMIx to change
this pipeline" (`RevisePanel`) and Auto Pipeline's description. Press to speak,
press again to stop; it shows the seconds while recording, a spinner while the clip
is transcribed, and any failure as an alert above it. It renders nothing where the
browser cannot record (`canRecordVoice()`). `useVoiceInput(onTranscript)` owns the
microphone: `getUserMedia`, a `MediaRecorder`, a stop after `MAX_RECORDING_SECONDS`
(180), and, once stopped, `toSpeechWav` then `core/api/voice.transcribeClip`; the
words go to the latest `onTranscript` (`useLatest`). Unmounting releases the
microphone and drops a transcription on its way. `wav.ts` converts the recording
(WebM, Ogg or MP4, whatever the browser made) to what Meta's speech model reads:
decoded with `AudioContext`, re-rendered by an `OfflineAudioContext` into one 16 kHz
channel, written as 16-bit PCM WAV by `encodeWav`. `dictation.ts`
(`appendDictation`) adds the words after what is typed, within the box's limit. The
server sends `Permissions-Policy: microphone=(self)`, so only the app's own pages
may ask for the microphone. Tests swap the real button for `speakingMic.tsx`, whose
button "says" `SPOKEN` (`vi.mock(…/MicButton, () => import(…/speakingMic))`).

## `core/ui/` — shared presentation and motion

Components here render and animate; they never fetch or touch storage.

| File | Role |
|---|---|
| `brand.ts` | `BRAND_COLORS` (the logo's sky → indigo → purple) for WebGL, canvas and inline gradients |
| `GlowButton.tsx` | Primary call to action: brand gradient, StarBorder while usable, ClickSpark, `busy` spinner. One per view. Also exports `glowButtonClass` / `BUTTON_SIZES` (sm, md, lg), the single source for the button look |
| `GlowLink.tsx` | `GlowButton`'s look on a router `Link`, for navigation that should stay a real link |
| `TiltCard.tsx` | Leans its children toward the pointer in 3D; flat on touch and under reduced motion |
| `webgl.ts` | `hasWebGL()`: probes for a context and releases it, so effects can pick a fallback |
| `ActivePill.tsx` | Selected-item highlight shared through a motion `layoutId`, so it glides between nav items, tabs and pickers |
| `PageTransition.tsx` | Enter-only fade/slide keyed by the route |
| `AmbientBackdrop.tsx` | Fixed, static glow behind the signed-in screens |
| `AppFrame.tsx` | The signed-in frame: the fixed sidebar from `lg` up; below it, the 60px top bar and the menu drawer (see Routing) |
| `SidebarNav.tsx` | The sections in labelled groups (`NavGroup`, `NavItem` with an optional `badge`), the current one marked `aria-current` and highlighted |
| `Page.tsx` | `Page` (padding and the `max-w-6xl` column) and `PageHeader` (`h1`, a description, extras under it) for every standard screen |
| `screen.ts` | `FULL_SCREEN_HEIGHT`: the height of a full-window screen, below the top bar or beside the sidebar |
| `BusyNotice.tsx`, `Spinner.tsx` | Loading line with shimmer text; the spinner (`decorative` hides it inside a labelled control) |
| `CostText.tsx` | A cost (`describeCost` from `core/usageFormat`) as plain words, its token counts in the `title` and also read out after it, so nothing depends on the pointer. `compact` uses the short words ("Cost unknown") for tight rows |
| `SwitchButton.tsx` | The bare `role="switch"` button: `checked`, `disabled`, `onChange(next)`, and its name from `label`, or from the visible text it points to with `labelledBy` and `describedBy`. The one switch every other is built on |
| `ToggleSwitch.tsx` | A `SwitchButton` with its state in words ("On" / "Off") beside it: `checked`, `label` (its accessible name), `disabled`, `onChange(next)`. Shared by the integrations and the schedules |
| `AiNotice.tsx` | The one line that says text beside it was written by AI and can be wrong (`AI_NOTICE`, EU AI Act art. 50): under the chat composer, and once at the head of a run report's deliverables |
| `motionTokens.ts` | The motion scale for `motion/react`, mirroring transitions.dev: `DURATION` (quick 150 ms, fast 250, medium 350, slow 400), `EASE_SMOOTH_OUT` (the same curve as `--ease-smooth-out`, Tailwind's `ease-smooth-out`), `DISTANCE` (micro 4px, base 8px), `BLUR` and `ICON_SPRING` |
| `focus.ts` | `FOCUS_RING` (the 2px sky ring under keyboard focus) and `TOUCH` (40px tall under a mouse, 44px under a finger), the one copy of each class string |
| `Heading.tsx` | `Heading level={2…6}`: a heading whose level the caller computes (the run report nests under the page's) |
| `SwapText.tsx` | Words that change in place: the old ones rise out with a slight blur, the new ones rise in (150 ms each); only a fade under reduced motion; nothing on the first render |
| `Announcer.tsx` | A polite, atomic `role="status"` line portalled into `<body>`, so what it says is heard even while its owner is hidden (the run report's announcements) |
| `LegalLinks.tsx` | The three legal pages as a row of small links (`LEGAL_LINKS`): on the sign-in and sign-up cards, under every Settings tab and on the legal pages themselves |

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
- Timings come from the token scale (`core/ui/motionTokens.ts`, and `duration-150` /
  `duration-250` / `ease-smooth-out` in CSS): 150 ms for a close or a text swap, 250 ms
  for an open, 350–400 ms for a panel or a document arriving; content arrives 8px below
  its place, text swapping in place moves 4px, and a blur is at most 2px. Closing is
  faster than opening. Under reduced motion keep at most a 150 ms fade: no movement, no
  blur. Enter with `initial={false}` where a component mounts with the page, so nothing
  animates on load, and transition named properties (never `transition: all`). The run
  report's moments (M1–M13) are listed in
  [frontend-missions.md](frontend-missions.md#the-run-report-featuresrunsreport).
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

### `features/mission`

The Missions workspace at `/mission` and `/mission/<pipeline id>`: the conversation, the
team, the results, their layouts and what is kept. It has its own page,
[frontend-missions.md](frontend-missions.md#featuresmission--the-missions-workspace),
with the run report the Results pane shares with the Runs page and the builder.

### `features/chat`

The Chat screen at `/chat`, over the chats the server keeps: the list, the open chat,
its replies' tools and cost, and what the tab remembers. It has its own page,
[frontend-chat.md](frontend-chat.md).

### `features/pipelines`

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
| `PendingApprovals.tsx`, `ApprovalCard.tsx`, `ArgumentList.tsx`, `approvalFormat.ts` | Approval gates. `PendingApprovals` lists a run's `pending_approvals` under the report's header (the report's `Announcer` says how many wait; `askedBy` names the step and role that asks), each as an `ApprovalCard`: its question first (`Allow “Send email”?`, or for AIMIx's own tools a plain one, "Save “notes/plan.md” to your files?"; focusable, `id="approval-{id}"`, the target of "Review the request"), who asks ("Draft (Writer) wants your OK first.") and from which integration, the tool's description (not for a plain ask), what it will use (`ArgumentList`: one labelled value per argument, a long one folded behind "Show all" in a native `<details>`), **Approve** and **Decline** with "Approving…" / "Declining…" states, and "{time left} · No answer counts as a decline." (ticking, `useNow`). `approvalFormat.ts` holds the pure helpers (`toolLabel`, `argumentRows`, `formatTimeLeft`: "5 h 56 min left") |
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
terms of use and the privacy policy before the account is created.

### `features/legal`

The three public legal pages, in French: `LegalPage` picks the document by path
and renders it through `renderMarkdown`, with a "Version provisoire" note while
an operator fact is missing. `operator.ts` holds those facts (`null` shows as a
visible "[à compléter : …]" marker), `documents/` the Markdown texts with
`{{fact}}` placeholders, `fillFacts.ts` the substitution (an unknown placeholder
throws). What to fill in and what keeps the texts true: [legal.md](legal.md).

## Conventions (from AGENTS.md §8)

- No `fetch` in components; no `localStorage` outside `tokenStorage.ts`.
- Payload types only in `core/api/types.ts` (the planning and auth payloads live in
  `planningTypes.ts`, `authTypes.ts` and `pipelineTypes.ts` and are re-exported from
  it, so imports stay the same).
- Every effect that starts async work cancels it (`active` flag or
  `AbortController`).
- Tailwind utilities first; Prettier: 100 cols, single quotes.

## Tests

`npm test` (Vitest, jsdom). Existing suites include `App.test.tsx`,
`core/api/client.test.ts` (auth header, error contract, 401 handling and when it
ends the session, network error), `core/auth/AuthContext.test.tsx` (signing out when
the session ends or on logout, no loop on public pages, forgetting mission drafts),
`core/auth/tokenStorage.test.ts`, `core/markdown/renderMarkdown.test.ts` (sanitisation,
through both renderers: injected forms, styles, classes and links; what Markdown makes
still renders; `renderDocument`'s heading levels, table scrollers and number cells),
`documentText.test.ts` and `RenderedMarkdown.test.tsx`, `core/hooks/useCopyToClipboard.test.tsx`
(rich, plain and refused copies, the timer), `core/ui/motionTokens.test.ts` (the JS and CSS
curves agree), `SwapText.test.tsx`, `Announcer.test.tsx`, `Heading.test.tsx`,
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
and `integrationDraft.test.ts`, and `WebhooksSection.test.tsx` for webhooks; `testData.ts` holds their fixtures and `byPath`,
a fetch stand-in that answers each API path. For
runs: `core/api/runs.test.ts`, `features/runs/useRun.test.tsx` (polling with
fake timers, abort on unmount, stop, resume, adopt), `useLatestRun.test.tsx` (`checked`
and `listed`, failure paths included), `toolWords.test.ts` and `RunsPage.test.tsx` (list,
deep link, delete with confirmation);
`features/runs/testData.ts` builds the runs and requests they share (`runStep(order, status,
output, used)` and `makeRun` default to nothing used; `usageOf(in, out, cost)`
builds a usage). Tokens and cost: `core/usageFormat.test.ts` (formatting,
parsing what a person types, the words for each kind of cost),
`core/ui/CostText.test.tsx`, `core/api/usage.test.ts`,
`features/runs/report/RunReportUsage.test.tsx` (the running total, per-agent cost,
unknown and partial costs, the stop at a limit and raising it), `runBudget.test.ts`,
`ResumeControl.test.tsx` (raise the limit and resume), `useRunResume.test.tsx`,
`RunHistoryUsage.test.tsx`, `features/pipelines/RunCostLimit.test.tsx` (the run
form's limit field and its draft rules) and
`features/settings/UsageSection.test.tsx` (the section, and `useUsage`
cancelling on unmount).
For approval gates: `core/api/approvals.test.ts`, `approvalFormat.test.ts`,
`ApprovalCard.test.tsx` (the words, folded values, the countdown, busy and
read-only states, the plain ask, the jump target), `PendingApprovals.test.tsx`,
`useRunApprovals.test.tsx` (answering through `useRun`), `RunsPageWaiting.test.tsx`
(a waiting run in the history and its detail, approve, decline and a
refused answer), `useWaitingRuns.test.tsx`, `core/ui/SidebarNav.test.tsx` and
`App.test.tsx` (the badge), and `features/settings/IntegrationApproval.test.tsx` (the switch).
`App.test.tsx` stubs `useWaitingRuns`: it answers fetch calls in order, for each
screen alone, and sets the count itself.
The mission workspace is
covered by `features/mission/`: the pure modules (`missionIntent.test.ts`,
`teamBrief.test.ts`, `missionStorage.test.ts`), the hooks (`useMissionTeam.test.tsx`:
loading, one save at a time, autosave, identity kept; `useMission.test.tsx`: describe →
reply, revise → apply or discard, saving then starting a run, reopening a mission,
templates, "Open in builder"), the components (`MissionTabs.test.tsx`,
`StepDrawer.test.tsx`, `PlannedDeliverables.test.tsx`, `ComposerAttachments.test.tsx`,
`ComposerTouch.test.tsx`, `InputsMessageView.test.tsx`), the layouts (`missionPanes.test.ts`,
and `MissionLayout.test.tsx`: three panes, two columns, settling once, when Results comes
forward without moving focus) and the whole screen (`MissionPage.test.tsx`: starting,
describing, change requests, running; `MissionPanes.test.tsx`: tabs and focus, the drawer,
the results pane and its files, addresses and what a tab remembers).
The run report is covered by `features/runs/report/`: the pure modules (`reportModel`,
`reviewRounds`, `outcomeCopy`, `signOffCopy`, `stepCopy`, `runGiven` (with the server's
real notes), `runFiles` (the time window), `deliverableFiles`, `jump`), the parts
(`DeliverableList` with the hand-over's motion and reduced motion, `DeliverableActions`,
`DeliverableSlot`, `RunFiles`, `RunGiven`, `TeamWork`), the announcements
(`useRunAnnouncements.test.ts`) and the whole report in each state (`RunReport.test.tsx`,
`RunReportFlow.test.tsx`: the check and its rounds, `RunReportUsage.test.tsx`); the builder's
use of it is in `features/pipelines/PipelineBuilderRun.test.tsx`. `App.test.tsx` checks the nav order and the
Missions route, `features/auth/LoginPage.test.tsx` the landing after sign-in,
`features/pipelines/OpenInMissionLink.test.tsx` the builder's link and
`core/hooks/useMediaQuery.test.tsx` the media-query hook, `core/hooks/useFileDrop.test.tsx` the drop zone, `core/chosenFiles.test.tsx` a file input taking the same file twice.
For conditions and review loops: `core/api/pipelines.test.ts` (older pipelines and plans read as
having neither), `stepFlow.test.ts` (the operator registry, which sources a condition may
use, the words for a condition and a review, which loops the engine follows and how
many rounds each step may take), `stepFlowProblems.test.ts` and `stepFlowEdits.test.ts`
(each refusal in plain words; removing a step, renumbering and a new stage keep
every condition and review pointing where it did), `StepFlowFields.test.tsx` (folded
until opened, the fields, stale choices kept, problems announced, a review offered
from the second stage on), `PipelineGraph.test.tsx` and `pipelineGraph.test.ts` (the
marks, the loop-back rail, legend, labels and the model behind them),
`features/runs/report/RunReportFlow.test.tsx` (a skipped deliverable and its reason,
"Done, with no deliverable", the reviewer's sign-off and rounds), `roundNotes.test.ts`, and
the planned steps in
`GeneratedSteps.test.tsx`; `StepDrawer.test.tsx` and `missionStorage.test.ts` cover
the mission side.
For schedules:
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

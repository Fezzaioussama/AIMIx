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
    auth/           # LoginPage, RegisterPage, ForgotPasswordPage, ResetPasswordPage, AuthCard, AuthLayout
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
| `/forgot-password` | `ForgotPasswordPage` (asks for the account's address; the server emails a reset link) | public |
| `/reset-password` | `ResetPasswordPage` (`?token=…` from the link: a new password, once) | public |
| `/shared/:token` | `SharedRunPage` (lazy-loaded; one run's report by its share link, read-only: `RunReport` without controls) | public |
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

Each feature folder is described in [frontend-features.md](frontend-features.md):
mission, chat, pipelines, templates, files, runs, schedules, settings, landing,
auth and legal.

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
integrations `IntegrationOAuth.test.tsx` (the card's sign-in states, the notice read back
from the URL), `IntegrationsSection.test.tsx` (list, add, validation, test
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
read-only states, the plain ask, the jump target), `QuestionCard.test.tsx` (the question,
its suggested answers, an answer of their own, Skip, read-only), `PendingApprovals.test.tsx`,
`useRunApprovals.test.tsx` (answering through `useRun`), `report/FeedbackRow.test.tsx`
(nothing while the run works, the thumbs, the note), `ShareRunButton.test.tsx` and
`features/share/SharedRunPage.test.tsx` (the link made, copied and withdrawn; the
read-only page and a withdrawn link), `RunsPageWaiting.test.tsx`
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
Missions route, `features/auth/LoginPage.test.tsx` the landing after sign-in and its reset link,
`ForgotPasswordPage.test.tsx` and `ResetPasswordPage.test.tsx` the reset flow (the request
and its status, a refusal, the token and the new password, a missing token),
`features/settings/EmailBlock.test.tsx` the address, its removal, the switch and a refusal,
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

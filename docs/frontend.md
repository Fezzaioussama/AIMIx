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
    hooks/          # useModels.ts, useAgentTools.ts, useCancellableRequest.ts, useLatest.ts, useNow.ts, useMediaQuery.ts, useMountedRef.ts
    markdown/       # renderMarkdown.ts
    routes.ts       # HOME_PATH (where sign-in lands), missionPath(id), LEGAL_LINKS
    saveBlob.ts     # hands a downloaded Blob to the browser as a file to save
    time.ts         # elapsedMs, formatDuration, formatDateTime
    usageFormat.ts  # formatCost, formatTokens, parseCost, describeCost: tokens and costs in words
    ui/             # shared presentational components and motion (no data access)
      reactbits/    # effects adapted from React Bits, with its LICENSE.md
  features/
    auth/           # LoginPage, RegisterPage, AuthCard, AuthLayout
    landing/        # the public front page at /: sections, content/, scene/ (3D hero)
    chat/           # ChatPage, ChatMessages, ChatComposer, useChatStream
    files/          # FilesPage, UploadPanel, FileRow, useFiles, fileFormat
    legal/          # LegalPage: /legal, /privacy, /terms (French), operator facts
    mission/        # MissionPage: the front door, one screen from describing a mission to its results
    pipelines/      # PipelineBuilderPage, AutoPipelinePage, hooks, subcomponents
    runs/           # RunsPage, LiveRun, useRun and the run history
    schedules/      # the Schedule panel (builder) and the Schedules view of the Runs screen
    settings/       # SettingsPage: LLM providers, Integrations (users' MCP servers), Usage, Account
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
| `/runs/schedules` | `SchedulesPage` (a fixed path, so it wins over `:runId`; `SCHEDULES_PATH`) | guarded |
| `/settings` | `SettingsPage` | guarded |
| `*` | redirect to `/login` | — |

Guarded routes render inside `AppShell`: a static `AmbientBackdrop`, the fixed
top nav (its highlight slides between items; "Pipelines" covers the pipeline
screens, the template gallery and the run history, including the routes below
them such as `/runs/7` and `/runs/schedules`; "Missions" covers `/mission` and `/mission/7`) and the
`RequireAuth` outlet, which `PageTransition` eases in when the first path segment
changes (so `/runs` → `/runs/7` and `/mission` → `/mission/7` keep the page
mounted). `/mission` is the front door: signing in (`LoginPage`) and "Open the
app" on the landing page both go to `HOME_PATH` from `core/routes.ts`.

**The nav** holds Missions (first), Chat, Pipelines, Files and Settings. From `sm`
up it is a row of text. Below `sm` every item is its icon over a 10px label (the
icon comes from `core/ui/navIcons.ts`, by route, so `NAV_ITEMS` stays plain data;
an item without an icon gets a generic one) and "Log out" is an icon, still named
"Log out": five items, the logo and the exit fit 390px and 360px phones. Every item
keeps its visible text as its accessible name. A sixth item must be checked at
360px before it is added.
`RequireAuth` checks `hasSession()` from storage directly, so a page reload
resolves the session before the first render without a redirect flash.

## `core/api/` — the gateway

| File | Contents |
|---|---|
| `endpoints.ts` | `API` object: **every** `/api/...` path. No other file may contain one. |
| `types.ts` | Payload interfaces: auth, pipelines, agent tools, run results with tool call metadata, runs (`Run` — with `pending_approvals` —, `RunStep` — a `StepResult` plus status, error, times and its tokens and cost — `RunSummary` with its `RunTrigger` and `schedule_id`, `RunPage`, `RunStatus` including `waiting`, `RunStepStatus`, which includes `skipped`, and `RunStep`'s `rounds` and `verdict`, `RunApproval`, `ApprovalStatus`), a step's `condition` and `review` (`StepCondition`, `ConditionOperator`, `StepReview`; every `PipelineStep` has both, `null` when unset), their usage and limits (`Usage`, `RunBudget`) and the usage report (`UsageReport`, `PipelineUsage`) and schedules (`Schedule`, `ScheduleTiming`, `ScheduleFrequency`, `ScheduleInput`, `SchedulePatch`, `SchedulePreview`). |
| `planningTypes.ts` | Planning payloads, re-exported from `types.ts`: `GeneratedPipelineResponse`, `MissionPlanResponse` (a team, or the planner's `ClarifyingQuestion`s), `PlanAnswer`, `PipelineChange`, `RevisedPipelineResponse`. |
| `client.ts` | `request<T>()` for JSON, `requestBlob()` for downloads and `streamText()` for streaming; `ApiError`. `request`, `requestBlob` and `streamText` share one send-with-refresh path. |
| `files.ts` | `listFiles`, `uploadFile` (one file, `replace` to overwrite), `downloadFile` (a `Blob`, fetched with the bearer header — never a token in a URL) and `deleteFile` |
| `auth.ts` | `login`, `register` |
| `chat.ts` | `streamChatReply` |
| `models.ts` | `fetchModels` |
| `agentTools.ts` | `fetchAgentTools` for the current pipeline tool catalogue |
| `pipelines.ts` | `listPipelines`, `getPipeline` (one by id, cancellable), `savePipeline`, `runPipeline` (the synchronous compatibility call; the screens start runs with `runs.ts`), `generatePipeline` (optional planner model and abort signal) and `revisePipeline` (1 h, `GENERATION_TIMEOUT_MS`; the latter takes an abort signal). `normalizePipeline` fills what older pipelines and plans leave out (inputs, role, tools, expected output, `condition` and `review` as `null`) |
| `templates.ts` | `listTemplates` and `createFromTemplate` (the caller's own pipeline from a template), both cancellable with a signal |
| `llmSettings.ts` | `fetchLLMSettings`, `saveLLMSettings`, `removeProviderKey` |
| `integrations.ts` | `listIntegrations`, `createIntegration`, `updateIntegration` (`PATCH`), `deleteIntegration`, and `testIntegration` (cancellable, `CONNECTION_TEST_TIMEOUT_MS` = 60 s, above the backend's 30 s `MCP_TIMEOUT_SECONDS`) |
| `documents.ts` | `extractDocument` (10 min, `UPLOAD_TIMEOUT_MS`, above the worst case for OCR of a long scan) and `DOCUMENT_FORMATS`, the one list of document kinds and extensions (mirroring the backend's `READERS`), with `DOCUMENT_ACCEPT` for a file input and `DOCUMENT_KINDS` for copy, landing page included |
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

## `core/hooks/useMediaQuery.ts` and `useMountedRef.ts`

`useMediaQuery(query)` is whether a CSS media query matches, kept current as the
window changes (`useSyncExternalStore`); it is `false` where the browser cannot
answer (jsdom), so tests render the narrow layout unless they stub `matchMedia`.
`useMountedRef()` is a ref that is true while the component is mounted, for the
answer of a request that cannot be cancelled (a save), which is then dropped
instead of updating state after the screen is gone.

## `core/hooks/useNow.ts` and `core/time.ts`

`useNow(ticking)` returns the current time, refreshed every second
(`CLOCK_TICK_MS`) while `ticking`, for live elapsed times. `time.ts` holds the
pure helpers screens share: `elapsedMs(startedAt, finishedAt, now)`,
`formatDuration(ms)` ("4.2 s", "3 min 05 s") and `formatDateTime(iso)`.

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

## `core/voice/` — dictation

`MicButton` sits in the Missions message box (`MissionComposer`): press to speak,
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
may ask for the microphone.

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
| `navIcons.ts` | `navIcon(route)`: the top bar's icon per section, used on a phone above each label |
| `BusyNotice.tsx`, `Spinner.tsx` | Loading line with shimmer text; the spinner (`decorative` hides it inside a labelled control) |
| `CostText.tsx` | A cost (`describeCost` from `core/usageFormat`) as plain words, its token counts in the `title` and also read out after it, so nothing depends on the pointer. `compact` uses the short words ("Cost unknown") for tight rows |
| `SwitchButton.tsx` | The bare `role="switch"` button: `checked`, `disabled`, `onChange(next)`, and its name from `label`, or from the visible text it points to with `labelledBy` and `describedBy`. The one switch every other is built on |
| `ToggleSwitch.tsx` | A `SwitchButton` with its state in words ("On" / "Off") beside it: `checked`, `label` (its accessible name), `disabled`, `onChange(next)`. Shared by the integrations and the schedules |
| `AiNotice.tsx` | The one line that says text beside it was written by AI and can be wrong (`AI_NOTICE`, EU AI Act art. 50): under the chat composer, above a pipeline's run results, under the mission's deliverables |
| `LegalLinks.tsx` | The three legal pages as a row of small links (`LEGAL_LINKS`): on the sign-in and sign-up cards, the Settings page and the legal pages themselves |

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

### `features/mission`

The mission workspace at `/mission` (a new mission) and `/mission/<pipeline id>`
(reopen one) is the front door: a person says what they want done, AIMIx builds a
team of agents, shows it, runs it and delivers the results, and the person changes
the team by talking to it. It adds no backend of its own: it composes generation
(`POST /api/pipelines/generate`), revision (`/revise`), saving and background runs,
on one screen.

**The screen.** Three panes side by side from `xl` (1280px); below that they are
tabs (Conversation, Team, Results — ARIA tabs, arrow keys, Home and End), and the
Results tab carries the newest run's status ("Running"). All three panes stay
mounted, so a half-written message and scroll positions survive a switch of tab;
a link in the conversation ("See the team") brings its pane forward and moves
focus to that pane's heading.

- **Conversation** (an ARIA `log`, so AIMIx's answers are announced). Empty, it asks
  "What do you want to get done?" with four example missions, the template
  quick-starts (one click makes the person's own saved pipeline from a template) and
  the newest saved missions. The first message *describes* the mission: a team is
  generated and, in plain words, AIMIx lists each agent, what it delivers, its tools
  and what the person provides. Every later message is a *change request*: AIMIx
  answers with the changes in words (`describeChange`), a preview, and inline Apply
  and Discard. **Run it** — the button under the box, or the phrase typed (`isRunRequest`
  takes whole phrases only, so "run the research in parallel" is still a change) —
  puts the run's inputs in the conversation (`RunInputCard`, "Attach a document"
  included) and starts the run. Nothing is sent while AIMIx is working (Stop cancels
  it), and the box says why.
- **Team.** The pipeline graph, live while a run works (a run of exactly this team,
  as in the builder). Selecting an agent opens a drawer over the results with the
  builder's own step editor (`StepCard`: role, task, tools, model, prompt); it is a
  non-modal dialog (focus moves in, Escape closes and hands focus back) and agents
  cannot be edited while a run works. "Open in builder" saves and opens the pipeline
  in the advanced mode, which links back with "Open in mission view".
- **Results.** The deliverables first (the newest run's output steps as `OutputCard`s,
  or what to expect before a run), then "Run details" — `LiveRun` embedded as it is,
  so anything added to it appears here: open while the run works or stopped short,
  folded once it is done (a fold or unfold by the person holds while the run stays in
  the same status) — then the newest workspace files with a link to Files. The pane's
  header keeps the run's status and Stop / Resume within reach.

**Layout rule.** The screen is exactly the window's height and each pane scrolls inside
itself, so nothing may make the page scroll. The grid has one bounded row
(`xl:grid-rows-[minmax(0,1fr)]`; without it the row grows with the tallest pane), every
scrolling area is `relative` (visually hidden `sr-only` text is absolutely positioned and
would otherwise escape it and stretch the page), each pane `overflow-clip`s what
decoration spills past its edge (the sparks around "Run it"), and the root clips what is
left. A new scrolling area inside a pane needs `relative` too.

**Saving.** A mission is a pipeline. A new mission is a draft in the tab until it
first runs: starting a run saves it (named from the plan, else from the first words
of the description) and moves the address to `/mission/<id>` without rebuilding the
screen (router state `{ adopted }`, see `useWorkspaceIdentity`); opening it in the
builder saves it too. Edits to a saved mission — the drawer, an applied change — are
saved `AUTOSAVE_DELAY_MS` (1.5 s) after the last one, and always before a run; one
save runs at a time. A failed save shows on the team pane and waits for the next edit.

**What is kept, and where.** The server keeps the team and its runs: reopening
`/mission/<id>` loads the pipeline and its newest run (`useLatestRun`). The
*conversation* is client state in this version: JSON in `sessionStorage`, one entry per
mission (`aimix.mission.v1.<pipeline id>`, or `….new` for a draft, which also keeps
the draft team), at most 200 messages, every access in try/catch. It lasts for the tab:
another tab or browser starts that mission's conversation again from a greeting with
its team. The keys name no account, so all of them are forgotten (`forgetAllMissions`)
when the session ends (a logout, or the server refusing the session) and again when
someone signs in: the next account in the tab never finds the last one's prompts, team
brief or draft team. A proposal that was waiting when the page was left shows as no longer
available, and a message left unanswered is said to be. Keeping conversations on the
server would need a table and endpoints; that is not part of this version.

| File | Role |
|---|---|
| `MissionPage.tsx`, `useWorkspaceIdentity.ts`, `missionAddress.ts` | The route: reads the id, redirects an address that is not one, and rebuilds the workspace when another mission is opened (not for a new mission's own first save) |
| `MissionWorkspace.tsx`, `usePanes.ts`, `missionPanes.ts`, `PaneHeader.tsx`, `MissionTabs.tsx` | The three panes and the phone tabs; which pane is in front and where focus goes; the pane title bar (screen readers only on a phone unless it has controls) |
| `useMission.ts` | The workspace's state, composed from the hooks below; routes what the person sends (describe, answer the planner's open questions, run it, or a change); opens the mission in the builder |
| `useMissionTeam.ts` | The team on screen: loads a saved mission by id, edits (swap, patch or remove an agent), one-at-a-time saving, autosave. Saving keeps the team's identity, so a proposal made for it stays valid |
| `useTeamGeneration.ts` | Description → team over `POST /api/pipelines/generate` (`planMission`): the planner may ask questions first (`may_ask`); the answers, or a skip, plan the team without asking again. Cancellable, plain words for failures, nothing saved |
| `useMissionProposals.ts` | Change requests over `useRevisePipeline`: each gets an answer in the conversation that shows the live proposal and keeps its outcome (applied, discarded, failed, stopped, expired) |
| `useMissionRun.ts` | "Run it": the inputs form in the conversation, saving then starting a run, following it (`useFollowedRun`) |
| `useMissionConversation.ts`, `missionMessages.ts`, `missionStorage.ts`, `missionShape.ts` | The conversation as plain JSON data (notes, team descriptions, the planner's questions, proposals, forms, runs), its `sessionStorage` copy, and `missionShape`'s checks of what is read back (a message or draft that does not fit is left out, never allowed to break the screen) |
| `missionIntent.ts`, `teamBrief.ts` | Pure: which phrases mean "run it"; a team as words (agents, tasks, tools, what to provide) |
| `ConversationPane.tsx`, `MissionComposer.tsx`, `MissionStart.tsx`, `useRecentMissions.ts` | The conversation pane: the log, the message box (Enter sends, Shift + Enter adds a line), the empty state with examples, templates and recent missions |
| `MessageItem.tsx`, `TeamMessageView.tsx`, `QuestionsMessageView.tsx`, `ProposalMessageView.tsx`, `InputsMessageView.tsx`, `RunMessageView.tsx`, `Bubble.tsx`, `messageContext.ts` | One view per kind of answer, in a registry (a new kind is a new entry); the context carries the live proposal, form, run and open questions each one needs. The questions view offers each suggested answer as a chip (a radio underneath) beside a field for one's own; a message typed meanwhile answers all of them |
| `TeamPane.tsx`, `StepDrawer.tsx`, `useStepDrawer.ts` | The team pane and the agent drawer (its editor is the builder's `StepCard`, so it has the two flow sections too, over the team's own steps); the hook follows the team (a removed agent closes it) and gives focus back |
| `ResultsPane.tsx`, `Deliverables.tsx`, `RunDetails.tsx`, `RecentFiles.tsx`, `useRecentFiles.ts` | The results pane: status and controls, deliverables (a skipped step is never one) followed by what each other agent produced (e.g. the orchestrator's final check), the folded live run, the newest files (reloaded when a run ends) |

`testData.ts` (fixtures and `routeFetch`, a fetch stand-in that answers
`"METHOD /api/path"`) and `testRender.tsx` serve the tests.

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
| `RecentPipelines.tsx`, `RunInputCard.tsx` | The builder's saved-pipeline list and its "Run Execution" panel: one labelled field per named input (all required), or a single free-text field when the pipeline declares none, then the optional cost limit. `RunInputCard` exports `RunInputFields` (those fields alone, with "Attach a document"; an optional `label` names the free-text field), which the schedule form asks its inputs with too, naming it "Input for each scheduled run" so the builder page never holds two fields called "Run input" |
| `CostLimitField.tsx` | The "Stop if it costs more than $…" field of the run form: optional, labelled, with its hint or problem under it as a polite live region. The draft keeps it as typed text (`RunDraft.maxCost`); `costLimitProblem` flags text that is not an amount above zero and `isRunReady` then blocks the run, because running without the cap the person asked for would be worse than not running. `runRequest` sends it as `max_cost_usd` |
| `StepHeading.tsx` | The title row of a step's card: name, position, model, Output badge (never on a skipped step) and, for a followed run's step, what its model calls cost (`CostText`; a pending step shows nothing), its "Round 2 of 3" chip when a review loop ran it again, and a reviewer's outcome ("Sent back 2 times, then accepted"; `roundNotes.ts`) |
| `FoldablePanel.tsx` | `PanelToggle` (the bar: a heading holding one button with an icon, a title and a chevron, `aria-expanded` / `aria-controls`) and `Foldable` (the body, animated by its grid row, `inert` while folded). `RevisePanel` and `SchedulePanel` are built on them |
| `usePipelineBuilder.ts` | State + transport: pipeline, saved list, dirty state, and actions for editing steps and inputs, adding parallel or following stages, replacing the whole draft (`replace`, for an accepted revision), saving and starting a run (`run` returns the started run for the page to follow). A changed pipeline must be saved before running. |
| `AutoPipelinePage.tsx` | Describe → generate → preview diagram → refine it in a sentence → edit inputs and steps → save |
| `useAutoPipeline.ts` | Generation, editing (including the planned inputs), adding or removing output steps, `replace` (an accepted revision) and saving the proposed workflow (later saves update it) |
| `RevisePanel.tsx` | "Ask AIMIx to change this pipeline": a foldable panel (open by default on the auto page) with the change box, clickable example instructions, a busy line with Stop, and the review. Ctrl/⌘ + Enter asks. Apply hands the revision to `onApply` (the page replaces its draft and leaves it unsaved); it never saves. Props: `pipeline`, `onApply`, optional `plannerModel`, `disabled`, `defaultOpen`, `headingLevel`. Mounted under the builder's title and under the auto page's diagram |
| `RevisionReview.tsx` | A proposal: the change list in plain words (added / changed / removed marks), a `PipelineGraph` preview, Apply and Discard; "Nothing to change" when the planner changed nothing. `ChangeList` is exported: the mission conversation shows the same list |
| `useRevisePipeline.ts` | `useRevisePipeline(pipeline)` → `{ proposal, stale, busy, error, propose, cancel, discard }` over `POST /api/pipelines/revise`. The proposal keeps the draft's id (so a save updates it) and only applies to the draft it was made from: an edit sets it aside (`stale`), and an answer for a draft edited meanwhile is dropped. Aborts on unmount and on `cancel` |
| `useRevisePanel.ts` | The panel's own state over `useRevisePipeline` (typed instruction, applied flag, `edit` / `pick` / `ask` / `apply` / `discard`) and `panelStatus`, the text of its live status line |
| `revision.ts` | `describeChange` (a change as a sentence), `adoptRevision`, the example instructions and the instruction length limit (mirrors the backend's) |
| `buttonStyles.ts` | Primary and secondary in-card button looks for actions beside a page's GlowButton |
| `PipelineInputsEditor.tsx` | The named run inputs (name, label, description), shared by both screens; names are typed as snake_case and problems show before saving |
| `pipelineInputs.ts` | Pure helpers for named inputs and attached documents (`appendDocument`, `documentSummary`): the naming rule (mirrors the backend), `{placeholder}` checks, the run form's `RunDraft`, and `runRequest`, which sends only declared inputs |
| `StepEditor.tsx` | Builder sidebar: each step's stage, title, expected output, agent role, tool access, model, prompt and, folded away, the two options that change how work flows (`StepFlowFields`). `StepCard` (one step's editor; it takes every step of the pipeline too) is exported: the mission screen's drawer uses it |
| `StepFlowFields.tsx`, `ConditionFields.tsx`, `ReviewFields.tsx`, `FlowFieldParts.tsx` | Two `<details>` sections, folded by default (the first file holds the sections, the next two their fields, the last the labelled field and the problem line they share): "Run this step only if…" (a source list: the previous result, each input, each earlier step by title; a comparison; the text, hidden for "is empty" / "is not empty") and "Review loop" ("Send the work back to stage [2 · Writer] up to [2 times] when this step says the work needs fixes", offered to a step with an earlier stage, plus one line saying its prompt should judge the work). Each shows what is set next to its title, and what is wrong in amber (`aria-invalid`, `aria-describedby`); a source or stage that is no longer on offer stays in its list, so the person sees what it was. Used by the step card (builder and the mission drawer) and by the planned steps |
| `stepFlow.ts`, `stepFlowProblems.ts`, `stepFlowEdits.ts`, `flowSources.ts` | The flow helpers. `stepFlow.ts`: the `CONDITION_OPERATORS` registry (the six comparisons in plain words), the limits (they mirror the backend's), `conditionSources`, `describeCondition` / `describeReview`, `reviewLoops` / `roundTotals` (which loops the engine follows and how many rounds each step may take: loops that cannot work or share a stage are dropped as the engine drops them). `stepFlowProblems.ts`: `conditionProblem` / `reviewProblem` in plain words (`SOURCE_CHECKS` is a registry like the engine's). `stepFlowEdits.ts`: editing renumbers steps and moves stages, and a condition names a step by number and a review a stage by number, so `withoutStep`, `followRenumbering` and `followNewStage` keep each pointing where it did (a condition whose step was removed is left looking at `step:0`, a step that does not exist, and the editor says so; nothing is moved onto another step or silently removed). `flowSources.ts` is their import-free leaf |
| `PromptPlaceholders.tsx` | Under a prompt: `{input}`, `{feedback}` (a reviewer's feedback when work is sent back) and the declared `{name}` placeholders, plus a warning for a placeholder nothing fills |
| `StepAgentFields.tsx` | Agent role and tool policy controls shared by manual and generated step editors (`null` all, `[]` none, selected names otherwise); the checklist groups tools by source, so an integration's tools sit under its name |
| `StepRoleFields.tsx` | A step's title, its Intermediate / Output toggle and its expected output, shared by both editors |
| `GeneratedSteps.tsx` | Generated steps drawn stage by stage; parallel steps side by side; each step shows the condition or review loop the planner gave it, editable like in the builder |
| `PipelineGraph.tsx`, `GraphNodeCard.tsx` | Flow diagram Input → stages → Outputs with fork/merge brackets, a legend and controls to add parallel steps or a following stage; the Input terminal lists the named inputs; nodes show title, model, status, an Output badge and, before a run, their expected output; clicking a finished (or failed) node opens its output (or error). Stages slide in; during a run connectors pulse and running nodes carry a StarBorder. `NODE_STATUS_STYLES` holds each status's colours and word: Not run, Waiting, Running, Done, Failed, Stopped, Skipped (muted and dashed, with "Its condition was not met" on hover). A step with a condition carries an "Only if…" mark (its words on hover and in its accessible name), a reviewer a "Reviewer" mark, and a step a followed run redid a "Round 2 of 3" mark. The legend explains the marks that are on the diagram |
| `LoopRail.tsx`, `graphLayout.ts` | The line that shows a reviewer sending work back: a row above the stages, from the reviewer's stage back to the stage it goes to, ending in an arrow into that stage with "Back here up to 2 times". It lines up with the columns because both read their widths from `graphLayout.ts` (stage columns have a fixed width), and it hides from assistive technology (the reviewer's node and the legend say the same in words). Drawn only for loops the engine would follow; it scrolls with the diagram on a phone |
| `pipelineGraph.ts` | Pure model behind the diagram (`buildGraph`, which takes a followed run's steps for live statuses and gives each node its condition, review, round and the most rounds it may take; a skipped node is never an output; `liveNodeStatus`) and the `OutputTarget` type |
| `PipelineRunView.tsx`, `RunStats.tsx` | Diagram + "Outputs" / "All steps" tabs + run stats (`RunStats`: outputs, steps, stages, seconds — counted up once the run has ended, with a one-line `sr-only` summary); deliverables are grouped by stage, and a run whose output steps were all skipped says so instead of "No outputs yet". It provides the `RunFlowContext` its step cards read. Given a followed run's `liveSteps` (and its `runKey`), nodes show each step's status, outputs appear as soon as they are saved, and "All steps" lists every step — a run in progress opens on it, a finished one on its outputs |
| `StepProgressCard.tsx` | In "All steps", a step without an output: its status, live elapsed time and, for a failed step, the error; for a skipped step "Skipped. Its condition was not met. It runs only if the previous result contains “blog”." |
| `RunFlowContext.tsx`, `roundNotes.ts` | The pipeline a followed run executed, handed to the cards of its steps by context (`PipelineRunView` and the mission's deliverables provide it) so a skipped step can say what its condition was and a step what its loop allows; and the words of a loop's outcome (`roundLabel`, `reviewNote`: "Sent back 2 times, then accepted") |
| `StepHeading.tsx` | Title row of a step's output card (name, model, Output badge) |
| `RunResults.tsx`, `ToolCallTrace.tsx` | Every step's output grouped by stage, with called tool names and success/error statuses |
| `OutputCard.tsx` | One output: rendered/raw toggle, copy, the input it saw, folding for long text |
| `useCopyToClipboard.ts` | Clipboard copy with short "Copied" feedback |
| `stages.ts` | `groupByStage`, `nextStage`, `insertStep` (which keeps conditions and review loops pointing where they did when it renumbers steps or opens a stage), `outputOrders` (preview of which steps are outputs; mirrors the backend rule) and `stepLabel` |
| `fieldStyles.ts` | The builder's field looks (`FIELD`, `INLINE_FIELD`, `SMALL_ACTION`) |
| `StageInput.tsx`, `StageHeader.tsx`, `StageArrow.tsx` | Stage picker, stage label ("N steps in parallel"), connector |
| `OpenInMissionLink.tsx` | On the builder's title, for a saved pipeline: "Open in mission view" (`/mission/<id>`); with unsaved edits it asks to save first instead |
| `PipelineNav.tsx` | Switch between Pipeline, Auto Pipeline, Templates and Runs; the Runs tab carries an amber count (and the same in words for screen readers) while runs wait for the person to approve an action (`useWaitingRuns`) |
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
| `useFiles.ts` | State + transport: loads the listing, uploads one file per request (so each refusal is reported against its file), replace/dismiss, download (then `saveBlob` from `core/saveBlob.ts`, shared with the account export) and delete (a 404 counts as deleted). One `AbortController` per mount cancels everything on unmount |
| `fileFormat.ts` | Pure helpers: `formatBytes` (decimal units like the server's limits), `formatDate`, `fileName`, `folderOf`, `fileIcon`, `describeTypes`, and `withFile` / `withoutFile`, which keep `used_bytes` equal to the sum of the sizes |

### `features/runs`

Runs execute on the server; the screens follow them by polling. `features/runs`
builds on the diagram pieces of `features/pipelines` (`PipelineRunView`,
`OutputCard`, `RunResults`), and the builder embeds its header and hooks.

| File | Role |
|---|---|
| `useRun.ts` | `useRun(runId)` → `{ run, error, busy, stop, resume(budget?), approve, decline, adopt }`. Fetches the run, polls it every `RUN_POLL_INTERVAL_MS` (1.5 s) while it is queued, running or waiting for an approval and stops once it ends; unmounting or switching runs clears the timer and aborts the request in flight. A resumed run is polled again; `approve(approvalId)` and `decline(approvalId)` answer a request and show the run as it comes back; `adopt(run)` shows a run already in hand (one just started) at once. A failed poll is retried, a 404 is not |
| `useLatestRun.ts` | The builder's follower: loads the pipeline's newest run when it opens (`GET /runs?pipeline_id=…&limit=1`) and `follow(run)` switches to a run started here |
| `useFollowedRun.ts`, `FollowedRunBar.tsx` | What the builder needs from that run: whether one is active, the run the diagram may show (`shown`, only a run of exactly the version on screen) and its duration; and its status bar with Stop, Resume and "Open in Runs", and a card for each action the run waits on, so it can be answered there |
| `useRunHistory.ts` | The history list: pages of `RUN_PAGE_SIZE` (20), refreshed every `RUN_LIST_REFRESH_MS` (5 s) while a listed run is active; `update` keeps a line in step with the open run, `remove` deletes a run |
| `LiveRun.tsx` | **The embeddable live run**: `<LiveRun run onStop onResume onApprove onDecline busy error actions>{children}</LiveRun>` — the run's own diagram with live statuses, the status bar, the cards of the actions it waits on, any `children` (e.g. its inputs), then the results. Pair it with `useRun` (`onApprove={live.approve}`, `onDecline={live.decline}`); without both, requests are shown but not answerable on that screen |
| `LiveRunHeader.tsx` | Status bar: status badge, "2 of 5 steps done" (a skipped step counts as done: "4 of 4 steps done (1 skipped)"), ticking elapsed time, the running cost (`RunCost`), Stop / Resume (`ResumeControl`) and extra `actions`, an `aria-live` line, and why the run stopped or waits (the failed step and its error, "Spending limit reached." with the server's message, "You stopped this run", "The server restarted…", "This run is waiting for you…") |
| `RunCost.tsx` | The run's cost in the status bar: `$0.0123` (its token counts a hover away, and read out), "$0.0123 or more" when part of it is unpriced, "Cost unknown for this model" when none is, next to "of $0.50 limit" when the run has a limit; nothing before an active run has used anything (or "Limit $0.50" if it has one), and "No usage recorded" for a finished run with none |
| `ResumeControl.tsx` | The Resume button. A run that stopped at its spending limit cannot resume under it, so it shows "Raise the limit to $[ ] Resume" instead, prefilled with double the old limit, saying what the run has used so far and refusing an amount at or below that; the token variant appears when it was a token limit. `onResume(budget?)` carries the new limit |
| `runBudget.ts` | `limitReached(run)` (which limit a run is at; mirrors the server's rule, rounding slack included), `limitParts`, `suggestedLimit`, `limitBudget` and `limitProblem` for the resume form, and `BUDGET_ERROR_CODE` |
| `PendingApprovals.tsx`, `ApprovalCard.tsx`, `ArgumentList.tsx`, `approvalFormat.ts` | Approval gates. `PendingApprovals` lists a run's `pending_approvals` under its status bar (a polite `aria-live` count), each as an `ApprovalCard`: "Needs your OK", `Allow “Send email”?`, which step and agent role asks and from which integration, the tool's description, what it will use (`ArgumentList`: one labelled value per argument, a long one folded behind "Show all" in a native `<details>`), the time left (ticking, `useNow`), **Approve** and **Decline** with "Approving…" / "Declining…" states, and "No answer counts as a decline". `approvalFormat.ts` holds the pure helpers (`toolLabel`, `argumentRows`, `formatTimeLeft`) |
| `useWaitingRuns.ts` | `useWaitingRuns()`: how many runs wait for the person, fetched on mount and every `WAITING_RUNS_POLL_MS` (5 s) with `countWaitingRuns`; a failed fetch keeps the last count, and unmounting clears the timer and aborts the request. `PipelineNav` shows it as a badge on the Runs tab, with the same count in words for screen readers |
| `RunStatusBadge.tsx` | A run status as a pill; `RUN_STATUS_STYLES` holds the words (Queued, Running, Waiting for you, Done, Failed, Stopped, Interrupted) and colours; "Waiting for you" is the one amber, pulsing pill of an active run |
| `runButtons.ts` | `RUN_BUTTON`: the looks of the run controls (stop, resume, neutral, danger) |
| `runStatus.ts` | `isActive` (queued, running, waiting), `isResumable` (mirroring the backend's status sets), `finishedStepCount` (succeeded or skipped), and `ranThisVersion(run, pipeline)` — whether a run executed exactly the pipeline on screen, conditions and review loops included |
| `RunsHeader.tsx` | The header both views of the Runs screen share: brand, the pipeline sub-navigation, and two underline tabs, History (`/runs`) and Schedules (`/runs/schedules`, `aria-current` on the one shown), then a line of text. The sub-navigation is unchanged, so it still fits a phone |
| `RunTriggerTag.tsx` | A small clock and "Scheduled" for a run a schedule started (`trigger === 'schedule'`); nothing for any other run. Shown beside the date in `RunHistoryList` and in `RunByline` |
| `RunByline.tsx` | The line under a run's title in `RunDetail`: "Started Oct 24, 9:58 PM · Scheduled · Open the pipeline" (the tag only for a scheduled run, the link only while the pipeline exists) |
| `RunsPage.tsx`, `RunHistoryList.tsx`, `RunDetail.tsx`, `DeleteRunButton.tsx` | The Runs screen: the list (pipeline, status, start, duration and cost) beside the open run on wide screens, one at a time on a phone (with "← All runs"); the detail shows the run's inputs and the live run; Delete asks "Delete this run for good?" with Keep focused, and is offered only once the run has ended |

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
| `SchedulesPage.tsx`, `useSchedules.ts` | The Schedules view: loading, an empty state that points to the builder, and the list; each outcome appears as a notice above the list, so a refusal is never below the fold. `useSchedules()` → `{ schedules, status, notice, actions }` with `update`, `setEnabled`, `remove` and `runNow` (which resolves to the started run, or `null`), over the settings' `useSubmission` (one busy flag, one notice). The list is fetched again every `ACTIVE_REFRESH_MS` (5 s) while a listed last run is queued or running and every `IDLE_REFRESH_MS` (30 s) otherwise, so a schedule that fires while the page is open shows up; the refresh pauses while a change is being saved (an older refresh can never put the old state back), a failed one is tried again, and everything is cancelled on unmount |
| `ScheduleList.tsx`, `ScheduleCard.tsx` | Each schedule as a card — its pipeline (a link to the builder), the timing in words, an on/off `ToggleSwitch`, "Next run" (or "Off. It will not run until you turn it on."), "Last run" (the date and a status badge, a link to the run), why the last time could not start, and Run now / Edit / Delete — or, while being edited, as its form with the pipeline's inputs, across the whole row. Delete asks first, with focus on "Keep it", which gives focus back to Delete; closing the form returns focus to Edit. "Run now" opens the run it started |
| `paths.ts` | `SCHEDULES_PATH`, the one place the route is written |

### `features/settings`

- `useLLMSettings()` loads `GET /api/llm-settings`, holds the form (active
  provider, a typed key and a model per provider) and saves it. `toUpdate()`
  sends only providers whose model changed or whose key was typed, so an
  untouched provider keeps following the server default. A typed key is cleared
  from the form once saved; the API never sends a key back.
- `SettingsPage` renders the provider picker and one `ProviderCard` (key
  status, password field, "Remove saved key", default-model select) each,
  then the Integrations, Usage and Account sections, and the legal links.
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
  signed in through `testRender.tsx` (`renderSettingsPage`).
- `useSubmission()` is the busy flag, notice and `submit(task, done, failed)`
  every section shares; `NoticeLine` shows the notice (`status`, or `alert` for
  an error).

Integrations (the user's own MCP servers):

| File | Role |
|---|---|
| `IntegrationsSection.tsx` | Heading, a plain-words explanation, the list, "+ Add an integration" and the section's notice |
| `IntegrationCard.tsx` | One server: name, host, an on/off `ToggleSwitch`, an "Ask me before its tools act" switch (on by default; says in words that chat cannot use the tools of an integration that asks), header names, the number of tools once tested, "Test connection", Edit, and Delete with an inline confirmation that takes focus ("Keep it") and gives it back |
| `ConnectionTestResult.tsx` | An always-present `aria-live` region: "Connecting…", the tools found (name and description), or why the test failed |
| `IntegrationForm.tsx`, `HeaderRows.tsx` | Add or edit: name (typed as snake_case), server URL, and header rows whose values are password fields; a saved value shows only as "Saved value ending in …", and is kept when its field is left empty |
| `integrationDraft.ts` | Pure helpers: the form draft, `draftProblem` (mirrors the backend rules: name pattern, URL, header names and values; every value again when the address changes), `toCreate`, `toPatch` (only what changed; a kept header is sent without its value) |
| `useIntegrations.ts` | Loads the list, creates, updates, switches on/off (`setEnabled`, and `setRequireApproval` for "Ask me before its tools act") and deletes through `useSubmission`, and keeps each connection test's result while the page is open (tests still running are cancelled on unmount) |
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
- Payload types only in `core/api/types.ts` (the planning payloads live in
  `planningTypes.ts` and are re-exported from it, so imports stay the same).
- Every effect that starts async work cancels it (`active` flag or
  `AbortController`).
- Tailwind utilities first; Prettier: 100 cols, single quotes.

## Tests

`npm test` (Vitest, jsdom). Existing suites include `App.test.tsx`,
`core/api/client.test.ts` (auth header, error contract, 401 handling and when it
ends the session, network error), `core/auth/AuthContext.test.tsx` (signing out when
the session ends or on logout, no loop on public pages, forgetting mission drafts),
`core/auth/tokenStorage.test.ts`, `core/markdown/renderMarkdown.test.ts` (sanitisation:
injected forms, styles, classes and links; what Markdown makes still renders),
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
`features/runs/testData.ts` builds the runs and requests they share (`runStep(order, status,
output, used)` and `makeRun` default to nothing used; `usageOf(in, out, cost)`
builds a usage). Tokens and cost: `core/usageFormat.test.ts` (formatting,
parsing what a person types, the words for each kind of cost),
`core/ui/CostText.test.tsx`, `core/api/usage.test.ts`,
`features/runs/LiveRunUsage.test.tsx` (the running total, per-step cost, unknown
and partial costs, the stop at a limit), `runBudget.test.ts`,
`ResumeControl.test.tsx` (raise the limit and resume), `useRunResume.test.tsx`,
`RunHistoryUsage.test.tsx`, `features/pipelines/RunCostLimit.test.tsx` (the run
form's limit field and its draft rules) and
`features/settings/UsageSection.test.tsx` (the section, and `useUsage`
cancelling on unmount).
For approval gates: `core/api/approvals.test.ts`, `approvalFormat.test.ts`,
`ApprovalCard.test.tsx` (the words, folded values, the countdown, busy and
read-only states), `PendingApprovals.test.tsx` (through `LiveRun` too),
`useRunApprovals.test.tsx` (answering through `useRun`), `RunsPageWaiting.test.tsx`
(a waiting run in the history, the Runs tab and its detail, approve, decline and a
refused answer), `useWaitingRuns.test.tsx` and `features/pipelines/PipelineNav.test.tsx`
(the badge), and `features/settings/IntegrationApproval.test.tsx` (the switch).
`TemplatesPage.test.tsx` and `App.test.tsx` stub `useWaitingRuns`: they answer
fetch calls in order, for their own screen.
The mission workspace is
covered by `features/mission/`: the pure modules (`missionIntent.test.ts`,
`teamBrief.test.ts`, `missionStorage.test.ts`), the hooks (`useMissionTeam.test.tsx`:
loading, one save at a time, autosave, identity kept; `useMission.test.tsx`: describe →
reply, revise → apply or discard, saving then starting a run, reopening a mission,
templates, "Open in builder"), the components (`MissionTabs.test.tsx`,
`StepDrawer.test.tsx`, `RunDetails.test.tsx`) and the whole screen
(`MissionPage.test.tsx`: starting, describing, change requests, running;
`MissionPanes.test.tsx`: tabs and focus, the wide layout, the drawer, the results pane,
addresses and what a tab remembers). `App.test.tsx` checks the nav order and the
Missions route, `features/auth/LoginPage.test.tsx` the landing after sign-in,
`features/pipelines/OpenInMissionLink.test.tsx` the builder's link and
`core/hooks/useMediaQuery.test.tsx` the media-query hook.
For conditions and review loops: `core/api/pipelines.test.ts` (older pipelines and plans read as
having neither), `stepFlow.test.ts` (the operator registry, which sources a condition may
use, the words for a condition and a review, which loops the engine follows and how
many rounds each step may take), `stepFlowProblems.test.ts` and `stepFlowEdits.test.ts`
(each refusal in plain words; removing a step, renumbering and a new stage keep
every condition and review pointing where it did), `StepFlowFields.test.tsx` (folded
until opened, the fields, stale choices kept, problems announced, a review offered
from the second stage on), `PipelineGraph.test.tsx` and `pipelineGraph.test.ts` (the
marks, the loop-back rail, legend, labels and the model behind them),
`features/runs/LiveRunFlow.test.tsx` (skipped steps and their reason, the round
chip, the reviewer's outcome, "No outputs" when the output steps were skipped, the
header's "(1 skipped)"), `roundNotes.test.ts`, and the planned steps in
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

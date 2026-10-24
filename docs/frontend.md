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
    hooks/          # useModels.ts, useAgentTools.ts
    markdown/       # renderMarkdown.ts
    ui/             # shared presentational components and motion (no data access)
      reactbits/    # effects adapted from React Bits, with its LICENSE.md
  features/
    auth/           # LoginPage, RegisterPage, AuthCard, AuthLayout
    landing/        # the public front page at /: sections, content/, scene/ (3D hero)
    chat/           # ChatPage, ChatMessages, ChatComposer, useChatStream
    pipelines/      # PipelineBuilderPage, AutoPipelinePage, hooks, subcomponents
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
| `/settings` | `SettingsPage` | guarded |
| `*` | redirect to `/login` | — |

Guarded routes render inside `AppShell`: a static `AmbientBackdrop`, the fixed
top nav (its highlight slides between items; "Pipelines" covers all three pipeline
routes) and the `RequireAuth` outlet, which `PageTransition` eases in on every
route change.
`RequireAuth` checks `hasSession()` from storage directly, so a page reload
resolves the session before the first render without a redirect flash.

## `core/api/` — the gateway

| File | Contents |
|---|---|
| `endpoints.ts` | `API` object: **every** `/api/...` path. No other file may contain one. |
| `types.ts` | Payload interfaces: auth, pipelines, agent tools, and run results with tool call metadata. |
| `client.ts` | `request<T>()` for JSON and `streamText()` for streaming; `ApiError`. |
| `auth.ts` | `login`, `register` |
| `chat.ts` | `streamChatReply` |
| `models.ts` | `fetchModels` |
| `agentTools.ts` | `fetchAgentTools` for the current pipeline tool catalogue |
| `pipelines.ts` | `listPipelines`, `savePipeline`, `runPipeline` and `generatePipeline` (1 h, `GENERATION_TIMEOUT_MS`) |
| `templates.ts` | `listTemplates` and `createFromTemplate` (the caller's own pipeline from a template), both cancellable with a signal |
| `llmSettings.ts` | `fetchLLMSettings`, `saveLLMSettings`, `removeProviderKey` |
| `integrations.ts` | `listIntegrations`, `createIntegration`, `updateIntegration` (`PATCH`), `deleteIntegration`, and `testIntegration` (cancellable, `CONNECTION_TEST_TIMEOUT_MS` = 60 s, above the backend's 30 s `MCP_TIMEOUT_SECONDS`) |

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
| `ActivePill.tsx` | Selected-item highlight shared through a motion `layoutId`, so it glides between nav items, tabs and pickers |
| `PageTransition.tsx` | Enter-only fade/slide keyed by the route |
| `AmbientBackdrop.tsx` | Fixed, static glow behind the signed-in screens |
| `BusyNotice.tsx`, `Spinner.tsx` | Loading line with shimmer text; the spinner (`decorative` hides it inside a labelled control) |

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
| `PipelineBuilderPage.tsx` | Builder screen: saved list, name, run inputs, steps, run form, diagram + results |
| `AttachDocument.tsx`, `useAttachDocument.ts` | "Attach a document" under every run input: choose a PDF, Word, HTML, CSV or text file, the server reads it (`core/api/documents.ts`), and its text is added to the input under a `[Document: name]` line, where it stays editable. The hook reads its callback when the file *finishes* (so text typed meanwhile is kept), replaces a file still being read, and cancels on unmount. Refusals show the backend's reason under that field |
| `RecentPipelines.tsx`, `RunInputCard.tsx` | The builder's saved-pipeline list and its "Run Execution" panel: one labelled field per named input (all required), or a single free-text field when the pipeline declares none |
| `usePipelineBuilder.ts` | State + transport: pipeline, saved list, run results, dirty state, and actions for editing steps and inputs, adding parallel or following stages, saving and running. A changed pipeline must be saved before running. |
| `AutoPipelinePage.tsx` | Describe → generate → preview diagram → edit inputs and steps → save |
| `useAutoPipeline.ts` | Generation, editing (including the planned inputs), adding or removing output steps and saving the proposed workflow (later saves update it) |
| `PipelineInputsEditor.tsx` | The named run inputs (name, label, description), shared by both screens; names are typed as snake_case and problems show before saving |
| `pipelineInputs.ts` | Pure helpers for named inputs and attached documents (`appendDocument`, `documentSummary`): the naming rule (mirrors the backend), `{placeholder}` checks, the run form's `RunDraft`, and `runRequest`, which sends only declared inputs |
| `StepEditor.tsx` | Builder sidebar: each step's stage, title, expected output, agent role, tool access, model and prompt |
| `PromptPlaceholders.tsx` | Under a prompt: `{input}` and the declared `{name}` placeholders, plus a warning for a placeholder nothing fills |
| `StepAgentFields.tsx` | Agent role and tool policy controls shared by manual and generated step editors (`null` all, `[]` none, selected names otherwise); the checklist groups tools by source, so an integration's tools sit under its name |
| `StepRoleFields.tsx` | A step's title, its Intermediate / Output toggle and its expected output, shared by both editors |
| `GeneratedSteps.tsx` | Generated steps drawn stage by stage; parallel steps side by side |
| `PipelineGraph.tsx`, `GraphNodeCard.tsx` | Flow diagram Input → stages → Outputs with fork/merge brackets, a legend and controls to add parallel steps or a following stage; the Input terminal lists the named inputs; nodes show title, model, status, an Output badge and, before a run, their expected output; clicking a finished node opens its output. Stages slide in; during a run connectors pulse and running nodes carry a StarBorder |
| `pipelineGraph.ts` | Pure model behind the diagram (`buildGraph`) and the `OutputTarget` type |
| `PipelineRunView.tsx` | Diagram + "Outputs" / "All steps" tabs + run stats (outputs, steps, stages, seconds — counted up, with a one-line `sr-only` summary); deliverables are grouped by stage |
| `StepHeading.tsx` | Title row of a step's output card (name, model, Output badge) |
| `RunResults.tsx`, `ToolCallTrace.tsx` | Every step's output grouped by stage, with called tool names and success/error statuses |
| `OutputCard.tsx` | One output: rendered/raw toggle, copy, the input it saw, folding for long text |
| `useCopyToClipboard.ts` | Clipboard copy with short "Copied" feedback |
| `stages.ts` | `groupByStage`, `nextStage`, `outputOrders` (preview of which steps are outputs; mirrors the backend rule) and `stepLabel` |
| `StageInput.tsx`, `StageHeader.tsx`, `StageArrow.tsx` | Stage picker, stage label ("N steps in parallel"), connector |
| `PipelineNav.tsx` | Switch between Builder, Auto and Templates |
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
| `IntegrationCard.tsx` | One server: name, host, an on/off `role="switch"`, header names, the number of tools once tested, "Test connection", Edit, and Delete with an inline confirmation that takes focus ("Keep it") and gives it back |
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
(fallbacks and accessible text of the adapted effects) and
`features/chat/ChatPage.test.tsx`, and for the landing page
`features/landing/LandingPage.test.tsx` (CTAs by sign-in state, tab keyboard
behaviour, FAQ disclosure, WebGL-less fallback), `useStepCarousel.test.ts` and
`scene/sceneLayout.test.ts` (the layout is deterministic and well-formed), and
for the gallery `features/templates/` (filters, the hook, and the page: busy
state, errors, retry and opening the builder). The
Settings page has `SettingsPage.test.tsx`, `useLLMSettings.test.tsx`, and for
integrations `IntegrationsSection.test.tsx` (list, add, validation, test
connection, delete confirmation, switch, edit with hints), `useIntegrations.test.tsx`
and `integrationDraft.test.ts`; `testData.ts` holds their fixtures and `byPath`,
a fetch stand-in that answers each API path.
`test-setup.ts` makes `getContext` return `null`, i.e. tests run as a browser
without WebGL or canvas, and stubs the observers jsdom lacks. Watch mode:
`npm run test:watch`.

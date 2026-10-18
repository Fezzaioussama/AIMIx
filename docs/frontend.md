# Frontend reference

React 19 + TypeScript (strict) + Vite 7, React Router 7, Tailwind CSS 4,
`motion` for animation, `marked` + `DOMPurify` for Markdown, Vitest + Testing
Library for tests.

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
    chat/           # ChatPage, ChatMessages, ChatComposer, useChatStream
    pipelines/      # PipelineBuilderPage, AutoPipelinePage, hooks, subcomponents
```

## Routing (`App.tsx`)

| Path | Page | Auth |
|---|---|---|
| `/login` | `LoginPage` | public |
| `/register` | `RegisterPage` | public |
| `/chat` | `ChatPage` | guarded |
| `/pipeline` | `PipelineBuilderPage` | guarded |
| `/auto-pipeline` | `AutoPipelinePage` | guarded |
| `/settings` | `SettingsPage` | guarded |
| `*` | redirect to `/login` | — |

Guarded routes render inside `AppShell`: a static `AmbientBackdrop`, the fixed
top nav (its highlight slides between items; "Pipelines" covers both pipeline
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
contains exact names, descriptions, and `AIMIx` or `MCP` sources; pipeline
steps store names rather than copying tool definitions.

## `core/markdown/renderMarkdown.ts`

`marked` → HTML → `DOMPurify.sanitize`. Model output is untrusted, so any
`dangerouslySetInnerHTML` must go through this function.

## `core/ui/` — shared presentation and motion

Components here render and animate; they never fetch or touch storage.

| File | Role |
|---|---|
| `brand.ts` | `BRAND_COLORS` (the logo's sky → indigo → purple) for WebGL, canvas and inline gradients |
| `BrandMark.tsx` | The animated "AIMIx" wordmark used by every header |
| `GlowButton.tsx` | Primary call to action: brand gradient, StarBorder while usable, ClickSpark, `busy` spinner. One per view |
| `ActivePill.tsx` | Selected-item highlight shared through a motion `layoutId`, so it glides between nav items, tabs and pickers |
| `PageTransition.tsx` | Enter-only fade/slide keyed by the route |
| `AmbientBackdrop.tsx` | Fixed, static glow behind the signed-in screens |
| `BusyNotice.tsx`, `Spinner.tsx` | Loading line with shimmer text; the spinner (`decorative` hides it inside a labelled control) |

`core/ui/reactbits/` holds components adapted from [React Bits](https://reactbits.dev)
(MIT + Commons Clause — keep `LICENSE.md` next to them): `Aurora` (WebGL2
background, split into `aurora/` shader, palette, program and renderer
modules), `GradientText`, `ShinyText`, `BlurText`, `RotatingText`,
`SpotlightCard`, `StarBorder`, `ClickSpark`, `CountUp`, `AnimatedContent`.
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
  blur is recomputed every frame. Animations start on mount: `whileInView`
  would need `IntersectionObserver`, which jsdom lacks.

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
| `PipelineBuilderPage.tsx` | Builder screen: saved list, name, steps, run input, diagram + results |
| `RecentPipelines.tsx`, `RunInputCard.tsx` | The builder's saved-pipeline list and its "Run Execution" panel |
| `usePipelineBuilder.ts` | State + transport: pipeline, saved list, run results, dirty state, and actions for editing, adding parallel or following stages, saving and running. A changed pipeline must be saved before running. |
| `AutoPipelinePage.tsx` | Describe → generate → preview diagram → edit → save |
| `useAutoPipeline.ts` | Generation, editing, adding or removing output steps and saving the proposed workflow (later saves update it) |
| `StepEditor.tsx` | Builder sidebar: each step's stage, title, agent role, tool access, model and prompt |
| `StepAgentFields.tsx` | Agent role and tool policy controls shared by manual and generated step editors (`null` all, `[]` none, selected names otherwise) |
| `StepRoleFields.tsx` | A step's title and its Intermediate / Output toggle, shared by both editors |
| `GeneratedSteps.tsx` | Generated steps drawn stage by stage; parallel steps side by side |
| `PipelineGraph.tsx`, `GraphNodeCard.tsx` | Flow diagram Input → stages → Outputs with fork/merge brackets, a legend and controls to add parallel steps or a following stage; nodes show title, model, status and an Output badge; clicking a finished node opens its output. Stages slide in; during a run connectors pulse and running nodes carry a StarBorder |
| `pipelineGraph.ts` | Pure model behind the diagram (`buildGraph`) and the `OutputTarget` type |
| `PipelineRunView.tsx` | Diagram + "Outputs" / "All steps" tabs + run stats (outputs, steps, stages, seconds — counted up, with a one-line `sr-only` summary); deliverables are grouped by stage |
| `StepHeading.tsx` | Title row of a step's output card (name, model, Output badge) |
| `RunResults.tsx`, `ToolCallTrace.tsx` | Every step's output grouped by stage, with called tool names and success/error statuses |
| `OutputCard.tsx` | One output: rendered/raw toggle, copy, the input it saw, folding for long text |
| `useCopyToClipboard.ts` | Clipboard copy with short "Copied" feedback |
| `stages.ts` | `groupByStage`, `nextStage`, `outputOrders` (preview of which steps are outputs; mirrors the backend rule) and `stepLabel` |
| `StageInput.tsx`, `StageHeader.tsx`, `StageArrow.tsx` | Stage picker, stage label ("N steps in parallel"), connector |
| `PipelineNav.tsx` | Switch between Builder and Auto |
| `modelLabel.ts` | Human-friendly label for a model id |

### `features/settings`

- `useLLMSettings()` loads `GET /api/llm-settings`, holds the form (active
  provider, a typed key and a model per provider) and saves it. `toUpdate()`
  sends only providers whose model changed or whose key was typed, so an
  untouched provider keeps following the server default. A typed key is cleared
  from the form once saved; the API never sends a key back.
- `SettingsPage` renders the provider picker and one `ProviderCard` (key
  status, password field, "Remove saved key", default-model select) each.

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
`features/chat/ChatPage.test.tsx`. `test-setup.ts` makes `getContext` return
`null`, i.e. tests run as a browser without WebGL or canvas. Watch mode:
`npm run test:watch`.

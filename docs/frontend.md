# Frontend reference

React 19 + TypeScript (strict) + Vite 7, React Router 7, Tailwind CSS 4,
`marked` + `DOMPurify` for Markdown, Vitest + Testing Library for tests.

```
frontend/src/
  main.tsx          # StrictMode → BrowserRouter → AuthProvider → App
  App.tsx           # route table, AppNav, AppShell
  styles.css        # Tailwind import + what utilities can't express
  core/             # cross-feature, the only layer that talks to the backend
    api/            # client.ts, endpoints.ts, types.ts, one module per resource
    auth/           # tokenStorage.ts, AuthContext.tsx, RequireAuth.tsx
    hooks/          # useModels.ts
    markdown/       # renderMarkdown.ts
  features/
    auth/           # LoginPage, RegisterPage, AuthCard
    chat/           # ChatPage, useChatStream
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
| `*` | redirect to `/login` | — |

Guarded routes render inside `AppShell` (fixed top nav + `RequireAuth` outlet).
`RequireAuth` checks `hasSession()` from storage directly, so a page reload
resolves the session before the first render without a redirect flash.

## `core/api/` — the gateway

| File | Contents |
|---|---|
| `endpoints.ts` | `API` object: **every** `/api/...` path. No other file may contain one. |
| `types.ts` | Payload interfaces: `AuthTokens`, `Pipeline`, `PipelineStep`, `StepResult`, `PipelineRunResponse`, `GeneratedPipelineResponse`, `ModelsResponse`. |
| `client.ts` | `request<T>()` for JSON and `streamText()` for streaming; `ApiError`. |
| `auth.ts` | `login`, `register` |
| `chat.ts` | `streamChatReply` |
| `models.ts` | `fetchModels` |
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

## `core/markdown/renderMarkdown.ts`

`marked` → HTML → `DOMPurify.sanitize`. Model output is untrusted, so any
`dangerouslySetInnerHTML` must go through this function.

## Features

### `features/chat`

- `useChatStream()` owns the transcript (`messages`), `isLoading`, and `send()`.
  `send` appends the user message and an empty AI message, then appends chunks
  as they stream. An `AbortController` in a ref cancels the stream on unmount.
- `ChatPage` renders the transcript (AI messages via `renderMarkdown`) and the
  input.

### `features/pipelines`

| File | Role |
|---|---|
| `PipelineBuilderPage.tsx` | Builder screen: saved list, name, steps, run input, diagram + results |
| `usePipelineBuilder.ts` | State + transport: `pipeline`, `saved`, `results`, `elapsedMs`, `status`, `message`, and `actions` (`reset`, `select`, `patchStep`, `addStep`, `removeStep`, `rename`, `save`, `run`). Requires a saved pipeline (`id`) before running. |
| `AutoPipelinePage.tsx` | Describe → generate → preview diagram → edit → save |
| `useAutoPipeline.ts` | `generated`, `status`, messages, `actions` (`generate`, `save`, `patchStep`, `rename`, `reset`) |
| `StepEditor.tsx` | Builder sidebar: each step's stage, title, role, model and prompt |
| `StepRoleFields.tsx` | A step's title and its Intermediate / Output toggle, shared by both editors |
| `GeneratedSteps.tsx` | Generated steps drawn stage by stage; parallel steps side by side |
| `PipelineGraph.tsx`, `GraphNodeCard.tsx` | Flow diagram Input → stages → Outputs with fork/merge brackets and a legend; nodes show title, model, status (not run / running / done) and an Output badge; clicking a finished node opens its output |
| `pipelineGraph.ts` | Pure model behind the diagram (`buildGraph`) and the `OutputTarget` type |
| `PipelineRunView.tsx` | Diagram + "Outputs" / "All steps" tabs + run stats (outputs, steps, stages, seconds); several outputs sit side by side |
| `StepHeading.tsx` | Title row of a step's output card (name, model, Output badge) |
| `RunResults.tsx` | Every step's output, grouped by stage |
| `OutputCard.tsx` | One output: rendered/raw toggle, copy, the input it saw, folding for long text |
| `useCopyToClipboard.ts` | Clipboard copy with short "Copied" feedback |
| `stages.ts` | `groupByStage`, `nextStage`, `outputOrders` (preview of which steps are outputs; mirrors the backend rule) and `stepLabel` |
| `StageInput.tsx`, `StageHeader.tsx`, `StageArrow.tsx` | Stage picker, stage label ("N steps in parallel"), connector |
| `PipelineNav.tsx` | Switch between Builder and Auto |
| `Spinner.tsx` | Loading indicator |
| `modelLabel.ts` | Human-friendly label for a model id |

### `features/auth`

`LoginPage` and `RegisterPage` share the `AuthCard` layout and call `useAuth()`.

## Conventions (from AGENTS.md §8)

- No `fetch` in components; no `localStorage` outside `tokenStorage.ts`.
- Payload types only in `core/api/types.ts`.
- Every effect that starts async work cancels it (`active` flag or
  `AbortController`).
- Tailwind utilities first; Prettier: 100 cols, single quotes.

## Tests

`npm test` (Vitest, jsdom). Existing suites: `App.test.tsx`,
`core/api/client.test.ts` (auth header, error contract, 401 handling, network
error), `core/markdown/renderMarkdown.test.ts` (sanitisation). Watch mode:
`npm run test:watch`.

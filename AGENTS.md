# AIMIx — Engineering Rules

**Canonical, agent-agnostic rules file.** It is the single source of truth for every coding
agent working in this repository — Claude Code, Codex, Cursor, Copilot, Gemini CLI, Aider,
any other assistant — and for human contributors. Edit the rules **here only**; the
per-agent entry points (see §10) must stay thin pointers, never copies.

These rules are **binding for every modification** in this repository: new features, bug
fixes, refactors, tests, one-line patches. Read them before writing code and verify them
before reporting a change as done.

If a rule blocks the task, do not silently ignore it: say which rule, why it conflicts, and
propose the alternative. Deviations are allowed only when stated explicitly in the response.

---

## 0. Workflow for every change

1. **Read before writing.** Locate the existing code that already does something similar
   (`grep` the layer, read the neighbours). Extending existing code beats adding new code.
2. **Place the change in the right layer** (see §2). A change in the wrong layer is wrong
   even when it works.
3. **Smallest diff that fully solves the task.** No unrelated reformatting, no renames that
   are not required, no speculative abstraction for needs that do not exist yet.
4. **Check the budgets** (§4) and the **Definition of Done** (§9) before finishing.

---

## 1. Non-negotiable rules (summary)

| # | Rule | Hard limit |
|---|------|-----------|
| 1 | DRY — no copy-pasted logic, no duplicated constants | 0 duplicated blocks |
| 2 | File size | **≤ 700 lines**, target ≤ 300 |
| 3 | Function / method size | ≤ 50 lines, ≤ 4 parameters |
| 4 | Cyclomatic complexity per function | ≤ 10 (≤ 3 nesting levels) |
| 5 | SOLID applied at class / module / component level | §5 |
| 6 | System-design boundaries respected | §6 |
| 7 | Design patterns used deliberately, never decoratively | §7 |
| 8 | No secrets, URLs, or tuning values hard-coded | env / settings only |

---

## 2. Project map — where code belongs

Put new code in the layer that owns the responsibility. Never skip a layer.

```
backend/
  api/
    urls.py              # routing table ONLY — no logic
    endpoints/*.py       # HTTP boundary: parse request, call a service, shape response
    services/*.py        # ALL business logic, orchestration, external calls (LLM)
    serializers.py       # validation + (de)serialization contracts
    models.py            # persistence + invariants that belong to the entity
    views.py             # re-export surface only (keep it a facade, no logic)
  server_llm/            # LLM provider layer: data_models.py (schemas) + server_llm.py
  backend/settings.py    # configuration from environment, no business values
frontend/src/
  main.tsx               # entry point: router + providers, no logic
  App.tsx                # route table + nav shell
  core/                  # cross-feature singletons, the only outward-facing layer:
    api/                 #   endpoints.ts (paths), types.ts (payloads),
                         #   client.ts (bearer token, timeout, error mapping),
                         #   one module per resource
    auth/                #   tokenStorage.ts (sole localStorage owner), context, route guard
    hooks/               #   shared data hooks
  features/<feature>/    # one folder per feature: pages, feature hooks, subcomponents
```

The repository is backend + frontend only. Automation engines (n8n or any other) are
not vendored or run here; if one is ever integrated, it is an external service reached
through an adapter in `services/` (§7), never a runtime checked into this repo.

**Layer rules**

- An `endpoints/` function must be thin: validate input, delegate to a service, map the
  result to a response. If it contains `if` branches about business meaning, HTTP calls, or
  prompt building, that code belongs in `services/`.
- `services/` must never import Django request/response objects. Services take and return
  plain Python types / dataclasses, so they stay testable and reusable.
- React components handle presentation and user interaction. Any `fetch` call, token
  handling, polling, or mapping of API payloads belongs in `core/api/` (or a
  `features/<feature>/use<Feature>.ts` hook if the state is feature-local). A component
  never calls `fetch` itself.
- Components must never read `localStorage` directly — go through `core/auth/tokenStorage`.
- No `/api/...` string literal outside `core/api/endpoints.ts`.

---

## 3. DRY — Don't Repeat Yourself

- **Rule of two:** the second time the same logic is needed, extract it. Do not wait for
  the third.
- Before writing a helper, search for an existing one. Duplicated helpers are worse than a
  slightly imperfect shared one.
- Extract to the right place:
  - shared backend logic → `api/services/` module (or a `api/services/common.py`-style
    helper module), not a copy in each endpoint;
  - shared HTTP/auth logic → `core/api/client.ts` (the single gateway), never a per-call copy;
  - shared markup → a small component; shared styles → a Tailwind utility class or a shared
    CSS layer, not a copy per component.
- **Single source of truth** for every value: endpoint paths, model names, retry counts,
  status enums, error codes. Declare once, import everywhere.
- Duplication that is *not* a DRY violation: two things that merely look alike today but
  change for different reasons. Do not couple them — note it in a comment if unclear.
- Tests may repeat setup for readability, but shared fixtures/builders are preferred.

---

## 4. Size budgets

- **File: hard cap 700 lines.** A file that would exceed 700 lines must be split *in the
  same change*, by responsibility — never by arbitrary "part 1 / part 2" cuts.
- Target sizes: Python module ≤ 300 lines, React component file ≤ 300 lines, function ≤ 50
  lines, class ≤ 200 lines. A component whose JSX outgrows the file should shed a
  subcomponent, and its data logic should move to a hook.
- Split strategies (in order of preference): extract a service/use-case module, extract a
  child component, extract a pure helper module, extract a strategy per variant (§7).

**Files already over budget (technical debt).** None — every file is currently within the
700-line cap, and the largest is `backend/server_llm/data_models.py` (179). When a file
first crosses a budget, list it here with its line count so the next change knows not to
grow it.

---

## 5. SOLID

**S — Single Responsibility.** One module = one reason to change. Concretely here: a service
that builds an LLM prompt does not also perform the HTTP call and does not also persist
the result. Split into prompt building / transport / persistence.

**O — Open/Closed.** Adding a new LLM provider or a new pipeline step kind must not
require editing an existing `if/elif` chain. Use a registry / strategy map
keyed by type, so a new case is a new entry, not a modified function.

**L — Liskov Substitution.** Any implementation of an interface must honour the contract:
same return shape, same error types, no new mandatory preconditions. An LLM provider that
raises a different exception type than its siblings breaks callers — normalise it.

**I — Interface Segregation.** Keep protocols narrow. A component that only needs
`listPipelines()` should not depend on a 20-method god service. Prefer several focused
services over one `ApiService`.

**D — Dependency Inversion.** High-level code depends on abstractions, not concretions.
Services receive their collaborators (HTTP client, LLM client, clock) via constructor or
parameter, so tests can substitute them. No `import requests` buried inside a business
function, and no `fetch` call inside a component — go through `core/api/`.

---

## 6. System design principles

- **Separation of concerns / clean layering.** Dependencies point inward:
  `endpoints → services → models/providers`. Never the reverse; no circular imports.
- **Stateless request handling.** No mutable module-level state to carry request data.
  State lives in the database, the session model, or the client.
- **Explicit contracts.** Every endpoint has a defined request and response schema via
  serializers, and a documented error shape `{ "error": "<code>", "detail": "<message>" }`.
  Keep error shapes consistent across endpoints.
- **Fail fast, degrade gracefully.** Validate at the boundary. Every outbound call (LLM
  provider, any other third-party API) must have an explicit **timeout**; decide and state the retry policy
  (bounded retries with backoff for idempotent calls only).
- **Idempotency.** Activate/deactivate/retry style operations must be safe to call twice.
- **Configuration via environment.** No URLs, keys, model names, or limits in code — read
  them from settings/env with a documented default in `backend/.env.example`.
- **Observability.** Log at boundaries with context (operation, id, duration, outcome), not
  inside tight loops. Never log secrets, tokens, or full prompt payloads with user data.
- **No blocking or long-running work in the request path.** Long generations must stream or
  be polled, not hold a request open indefinitely.
- **Backward compatibility.** Changing an API response shape or a model field requires a
  migration and a matching frontend update in the same change.
- **Least privilege.** Auth-protected by default; a new endpoint is public only if that is
  stated explicitly and intentionally.

---

## 7. Design patterns

Use a pattern when it removes a real, present problem (duplication, a growing `if` chain, a
hard dependency). **Name the pattern in a short comment or the PR description** so intent is
visible. Never add a pattern for ceremony — an unnecessary factory is a defect.

Preferred patterns for this codebase:

| Problem | Pattern | Where |
|---|---|---|
| Growing `if type == ...` over step/provider kinds | **Strategy + Registry** | `services/pipeline_runner.py` |
| Choosing an implementation by config (LLM provider, engine) | **Factory** | `server_llm/`, `services/llm.py` |
| Wrapping a third-party API behind our own contract | **Adapter / Gateway** | a dedicated module in `services/` |
| Multi-step build of a pipeline payload | **Builder** | `services/pipeline_generation.py` |
| Ordered, independently testable transformations | **Pipeline / Chain of Responsibility** | `services/pipeline_runner.py` |
| Data access shape shared by several services | **Repository** | around `models.py` |
| Cross-cutting HTTP concerns (auth header, error mapping, timeout) | **Gateway / Decorator** | `core/api/client.ts`; Python decorator for endpoints |
| State shared across components | **Provider / Context** | `core/auth/AuthContext.tsx` |
| Typed, immutable data across layers | **Value Object / DTO** (`@dataclass`, TS `interface`) | `server_llm/data_models.py`, frontend models |

Anti-patterns to reject: god class/service, anemic endpoint containing business logic,
singleton used as a global variable, deep inheritance (prefer composition), stringly-typed
branching, `any` as a habit in TypeScript, catching `Exception` and returning `200`.

---

## 8. Language & stack conventions

**Python / Django**
- Type hints on all public functions; `@dataclass` for structured data.
- Raise domain exceptions in services; translate them to HTTP status codes in `endpoints/`.
- Never catch a bare `except:`; catch the specific exception and re-raise or map it.
- Model changes always ship with the generated migration.
- f-strings, 4-space indent, imports grouped stdlib / third-party / local.

**TypeScript / React 19 (Vite)**
- Function components with hooks; `strict` TypeScript — no `any` unless justified in a
  comment. Prefer `unknown` plus a narrowing check in `catch`.
- Data fetching and mutation live in a hook or a `core/api/` module, never inline in JSX.
- Every effect that starts async work must cancel it on unmount (an `AbortController` or an
  `active` flag) — no state updates after teardown.
- Types for API payloads declared once in `core/api/types.ts` and imported, not redeclared
  per component.
- Tailwind utilities first; hand-written CSS only for what utilities cannot express
  (keyframes, rendered-Markdown styling).
- Never render model output with `dangerouslySetInnerHTML` unless it has been sanitised by
  `core/markdown/renderMarkdown`.

**No linter/formatter is configured yet.** Match the style of surrounding code. Frontend
formatting follows the Prettier config in `frontend/package.json` (100 cols, single quotes).

---

## 9. Definition of Done — verify before reporting

- [ ] No duplicated logic introduced; reused what already existed (§3).
- [ ] Every touched file ≤ 700 lines; over-budget files did not grow (§4).
- [ ] Functions ≤ 50 lines, ≤ 4 params, ≤ 3 nesting levels.
- [ ] Code sits in the correct layer; no inward/outward dependency violation (§2, §6).
- [ ] New branching on a "kind" uses a registry/strategy, not an `if` chain (§5 O, §7).
- [ ] External calls have timeouts; errors map to the standard error shape (§6).
- [ ] No secrets or environment-specific values in code; `.env.example` updated if needed.
- [ ] Migration generated for any model change; frontend updated for any contract change.
- [ ] Checks run and reported honestly (paste real output; never claim a check that was
      skipped):
  ```bash
  cd backend && uv run python manage.py check
  cd backend && uv run python manage.py test
  cd frontend && npm test
  cd frontend && npm run build
  ```
- [ ] Response states which rules were applied and any deviation with its reason.

---

## 10. Agent entry points

Every agent reads this same file. Most modern agents support the `AGENTS.md` convention
natively and need no extra wiring (Codex, Cursor, Zed, Aider, Jules, Gemini CLI).

| Agent | Entry point | Status |
|---|---|---|
| Any agent supporting the `AGENTS.md` convention | `AGENTS.md` | this file — canonical |
| Claude Code | `CLAUDE.md` | pointer: imports this file via `@AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` | add as a pointer if Copilot is used |
| Cursor (rules format) | `.cursor/rules/engineering.mdc` | add with `alwaysApply: true` if needed |
| Gemini CLI (`GEMINI.md` mode) | `GEMINI.md` | add as a pointer if needed |

**Rule for entry points:** a pointer file contains only a reference to `AGENTS.md` plus, at
most, agent-specific mechanics (which command to run, which tool to prefer). Rules content
duplicated into a pointer file is a DRY violation (§3) and will drift — delete it.

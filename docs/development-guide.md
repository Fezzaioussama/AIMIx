# Development guide

How to make a change in AIMIx that passes review. The binding rules are in
[AGENTS.md](../AGENTS.md); this page is the practical how-to.

## Daily loop

```bash
git checkout main && git pull
git checkout -b feat/<short-name>     # never commit straight to main

make run-aimix                        # work with the app running
# ... edit code, write tests ...

make format                           # ruff --fix + ruff format
make check                            # the full gate — must be green
git add -p && git commit
```

`make check` runs, in order: ruff lint + format check, mypy (`api`, `llm`,
`config`, `migrations`), pytest (which also checks that the Alembic migrations
match the models), Vitest, and the production frontend build.
Faster subsets while iterating:

```bash
uv run pytest backend/tests/test_pipeline_service.py -q     # one file
uv run pytest -k parse_plan -q                              # by name
cd frontend && npm run test:watch                           # Vitest watch
make typecheck                                              # mypy only
```

## Where does my change go?

| I want to... | Touch | Don't |
|---|---|---|
| Add or change an endpoint | schema in `api/schemas/` → service (logic) → thin route in `api/endpoints/` → router listed in `api/routes.py`; then `core/api/endpoints.ts`, `types.ts`, a function in `core/api/<resource>.ts` | Put logic or queries in the endpoint |
| Add a failure case | New `DomainError` subclass in `api/exceptions.py`; raise it from the service | Build a `Response` or raise `HTTPException` for an error |
| Query data differently | `api/repositories/` | Write `select(...)` in an endpoint, schema or service |
| Change a prompt | `api/services/prompts.py` | Build prompt strings in `pipelines.py` |
| Add a provider or model | `llm/` — see [llm-providers.md](llm-providers.md) | Add an `if provider ==` anywhere |
| Add a setting | A field on `Settings` in `config/settings.py`, document in `backend/.env.example` | Hard-code a URL, key, model id, or limit |
| Change a model field | `api/models.py` + an Alembic revision in the same commit | Edit an applied migration |
| Add a UI screen | `features/<feature>/` page + `use<Feature>.ts` hook, route in `App.tsx` | `fetch` or `localStorage` in a component |
| Share UI markup | A small component in the feature folder (or `core/` if cross-feature) | Copy-paste JSX |

## Recipe: add a backend endpoint (worked example)

Goal: `POST /api/pipelines/<id>/duplicate` returns a copy of an owned pipeline.

1. **Repository** — `api/repositories/pipelines.py`:
   ```python
   COPIED_FIELDS = ("order", "stage", "title", "is_output", "prompt", "model")


   def duplicate(session: Session, pipeline: Pipeline) -> Pipeline:
       steps = [{field: getattr(s, field) for field in COPIED_FIELDS} for s in pipeline.steps]
       return create_with_steps(session, pipeline.user, f"{pipeline.name} (copy)", steps)
   ```
2. **Endpoint** — `api/endpoints/pipelines.py` (the router is already
   protected in `api/routes.py`, so no auth code is needed):
   ```python
   @router.post("/{pipeline_id}/duplicate", status_code=201)
   def duplicate_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> PipelineOut:
       original = repository.get_owned(session, user, pipeline_id)
       return PipelineOut.model_validate(repository.duplicate(session, original))
   ```
3. **Route** — nothing to add: the route lives on the existing pipelines router.
   A new resource gets its own router, listed in `PROTECTED_ROUTERS`.
4. **Tests** — `tests/test_endpoints.py`: owner gets 201 and a new id; another
   user gets 404; unauthenticated gets 401.
5. **Frontend** — `endpoints.ts`:
   `duplicatePipeline: (id: number) => \`/api/pipelines/${id}/duplicate\``;
   `core/api/pipelines.ts`: `duplicatePipeline(id)` via `request<Pipeline>`;
   call it from `usePipelineBuilder`, not from the component.
6. **Docs** — add the endpoint to [api-reference.md](api-reference.md).
7. `make format && make check`.

## Recipe: change a model field

```bash
# edit backend/api/models.py
cd backend && uv run alembic revision --autogenerate -m "add pipeline tags"
# review backend/migrations/versions/<rev>_add_pipeline_tags.py, then
uv run alembic upgrade head       # or: make migrate
```

Commit the revision with the model change; `test_database.py` fails if they
disagree. If the field is exposed, update the schema in `api/schemas/`,
`frontend/src/core/api/types.ts`, and the UI in the same change.

## Writing tests

- **Never call a real provider.** Use the `fake_provider` fixture or
  `use_provider(app, FailingProvider(...))` (both override the provider
  dependency), or pass `FakeProvider` / `FailingProvider` directly to a service
  function. The test settings leave every provider key empty.
- Test the failure path too: e.g. `FailingProvider(ProviderTimeout("..."))` →
  expect `504` and `{"error": "provider_timeout", ...}`.
- Services are plain functions: test them without HTTP where possible
  (`test_pipeline_service.py` is the model).
- Frontend: mock `globalThis.fetch` with `vi.spyOn` as in
  `core/api/client.test.ts`.

Example backend test:

```python
def test_run_returns_each_step(auth_client, fake_provider, session, user, default_model):
    step = {
        "order": 1,
        "stage": 1,
        "title": "",
        "is_output": False,
        "prompt": "A {input}",
        "model": default_model,
    }
    pipeline = create_with_steps(session, user, "p", [step])
    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "x"})

    assert response.status_code == 200
    assert response.json()["final_output"] == "fake reply"
    assert fake_provider.calls == [("A x", default_model)]
```

## Size and quality budgets

Files ≤ 700 lines (target ≤ 300), functions ≤ 50 lines and ≤ 4 parameters,
complexity ≤ 10, nesting ≤ 3. If a file would cross a limit, split it by
responsibility in the same change. Details: AGENTS.md §4 and §9.

## Logging

Use the module logger (`logger = logging.getLogger(__name__)`) and log at
boundaries with `key=value` context (`pipeline.run pipeline_id=... duration_ms=...`).
Never log API keys, tokens, or prompt/user content. Level: `LOG_LEVEL`.

## Before opening a PR

- [ ] `make check` is green (paste the output in the PR).
- [ ] New behaviour has a test, including a failure case.
- [ ] Contract change → frontend types and UI updated in the same PR.
- [ ] Model change → migration included.
- [ ] New config → `backend/.env.example` updated.
- [ ] Docs in `docs/` updated if behaviour they describe changed.
- [ ] PR description names any design pattern introduced and any deviation from
      AGENTS.md, with the reason.

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
`config`), `manage.py check`, pytest, Vitest, and the production frontend build.
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
| Add or change an endpoint | serializer → service (logic) → thin endpoint → `api/urls.py`; then `core/api/endpoints.ts`, `types.ts`, a function in `core/api/<resource>.ts` | Put logic or queries in the endpoint |
| Add a failure case | New `DomainError` subclass in `api/exceptions.py`; raise it from the service | Build a `Response` for an error |
| Query data differently | `api/repositories/` | Write `.objects.filter` in an endpoint or serializer |
| Change a prompt | `api/services/prompts.py` | Build prompt strings in `pipelines.py` |
| Add a provider or model | `llm/` — see [llm-providers.md](llm-providers.md) | Add an `if provider ==` anywhere |
| Add a setting | `config/settings/base.py` via `env_*`, document in `backend/.env.example` | Hard-code a URL, key, model id, or limit |
| Change a model field | `api/models.py` + `makemigrations` in the same commit | Edit an applied migration |
| Add a UI screen | `features/<feature>/` page + `use<Feature>.ts` hook, route in `App.tsx` | `fetch` or `localStorage` in a component |
| Share UI markup | A small component in the feature folder (or `core/` if cross-feature) | Copy-paste JSX |

## Recipe: add a backend endpoint (worked example)

Goal: `POST /api/pipelines/<id>/duplicate` returns a copy of an owned pipeline.

1. **Repository** — `api/repositories/pipelines.py`:
   ```python
   @transaction.atomic
   def duplicate(pipeline: Pipeline) -> Pipeline:
       steps = [
           {"order": s.order, "prompt": s.prompt, "model": s.model}
           for s in pipeline.steps.all()
       ]
       return create_with_steps(user=pipeline.user, name=f"{pipeline.name} (copy)", steps=steps)
   ```
2. **Endpoint** — `api/endpoints/pipelines.py`:
   ```python
   @api_view(["POST"])
   @permission_classes([IsAuthenticated])
   def duplicate_pipeline(request: Request, pipeline_id: int) -> Response:
       original = repository.get_owned(authenticated_user(request), pipeline_id)
       copy = repository.duplicate(original)
       return Response(PipelineSerializer(copy).data, status=201)
   ```
3. **Route** — `api/urls.py`:
   `path("pipelines/<int:pipeline_id>/duplicate", duplicate_pipeline, name="duplicate_pipeline")`
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
cd backend && uv run python manage.py makemigrations api
uv run python manage.py migrate
```

Commit the migration with the model change. If the field is exposed, update the
serializer, `frontend/src/core/api/types.ts`, and the UI in the same change.

## Writing tests

- **Never call a real provider.** Use the `fake_provider` fixture (it patches
  `get_provider` in the endpoints) or pass `FakeProvider` / `FailingProvider`
  directly to a service function.
- Test the failure path too: e.g. `FailingProvider(ProviderTimeout("..."))` →
  expect `504` and `{"error": "provider_timeout", ...}`.
- Services are plain functions: test them without HTTP where possible
  (`test_pipeline_service.py` is the model).
- Frontend: mock `globalThis.fetch` with `vi.spyOn` as in
  `core/api/client.test.ts`.

Example backend test:

```python
def test_run_returns_each_step(auth_client, fake_provider, user, default_model):
    pipeline = create_with_steps(
        user=user, name="p", steps=[{"order": 1, "prompt": "A {input}", "model": default_model}]
    )
    response = auth_client.post(f"/api/pipelines/{pipeline.pk}/run", {"input": "x"}, format="json")

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
Never log API keys, tokens, or prompt/user content. Level: `DJANGO_LOG_LEVEL`.

## Before opening a PR

- [ ] `make check` is green (paste the output in the PR).
- [ ] New behaviour has a test, including a failure case.
- [ ] Contract change → frontend types and UI updated in the same PR.
- [ ] Model change → migration included.
- [ ] New config → `backend/.env.example` updated.
- [ ] Docs in `docs/` updated if behaviour they describe changed.
- [ ] PR description names any design pattern introduced and any deviation from
      AGENTS.md, with the reason.

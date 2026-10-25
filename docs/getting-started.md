# Getting started

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.10+ (pinned in `.python-version`) | Backend |
| [uv](https://docs.astral.sh/uv/) | recent | Python venv + dependency manager (`uv.lock`) |
| Node.js + npm | Node 20+ (tested on 24) | Frontend (Vite, React 19) |
| make | any | All commands are wrapped in the root `Makefile` |
| An LLM API key | — | OpenRouter (default) or TogetherAI |
| Tesseract (optional) | 4+, with the `eng` and `fra` languages | OCR of attached images and scanned PDFs, e.g. `apt install tesseract-ocr tesseract-ocr-fra`. Without it, everything else works; images are refused and scanned pages skipped, with a message saying OCR is not available |

## First-time setup

```bash
make install                           # uv sync  +  npm install in frontend/
cp backend/.env.example backend/.env   # then edit it (see below)
make migrate                           # create the schema (backend/aimix.sqlite3)
make run-llm                           # smoke test: prints the model list
```

### Minimum `.env` edits

Open `backend/.env` and set at least:

```dotenv
LLM_PROVIDER=openrouter          # or togetherai
OPEN_ROUTER_KEY=sk-or-...        # when LLM_PROVIDER=openrouter
TOGAI_API_KEY=...                # when LLM_PROVIDER=togetherai
```

Everything else has a working default for local development. Placeholder values
such as `your_api_key_here` or `change-me` are treated as **unset** by
`config/settings.py`, so a half-filled `.env` fails fast
with `provider_not_configured` instead of a confusing upstream 401.

Prefer not to keep the key in `.env`? Leave it unset, sign in, and open
**Settings** in the top bar: pick the provider, paste your API key and choose a
default model. It is stored encrypted for your account only and used from your
next request, with no restart. Anything you leave unset there falls back to
`backend/.env`. Saved keys are encrypted with `SECRET_KEY`, so changing it
means entering them again.

The full variable list, with comments, is `backend/.env.example`. An existing
`.env` from the Django version keeps working: `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS` and the other `DJANGO_*` names are still read.

### Chat's native pipeline tools

The chat agent always has three Python functions:

| Function | What it does |
|---|---|
| `list_pipelines()` | Lists your saved pipelines with ids, names, and step counts. |
| `inspect_pipeline(pipeline_id)` | Shows one of your pipelines, including its steps, prompts, and models. |
| `run_pipeline(pipeline_id, input_text)` | Runs one of your pipelines and returns its outputs and step results. |

These functions use the authenticated user's identity. The agent cannot inspect
or run another user's pipeline. Running a pipeline starts an agent for each step
and may take as long as a normal pipeline run; the run appears under **Runs**
like any other. Chat history is not persisted.

### Give chat and pipeline steps MCP tools

Chat uses a LangGraph agent with the same provider and default model as
pipelines (yours from Settings, else `LLM_PROVIDER`). Each pipeline step uses its selected model. Set `MCP_SERVERS` in
`backend/.env` to a JSON object. Each pipeline step can use all tools, no tools,
or a selected set according to its `allowed_tools` setting.
No server is configured by default. The connectors in a coding assistant or IDE
are separate and do not automatically become AIMIx server tools.

**These tools ask first.** An MCP tool can change something outside AIMIx, so by
default (`MCP_REQUIRE_APPROVAL=true`) a pipeline step that calls one waits for the
run's owner to approve it: the run shows **Waiting for you** and a card with the
tool and what it will use appears on the Runs page, with **Approve** and
**Decline**. The chat has no run to pause, so it is *not offered* those tools.
To let chat use the tools of `MCP_SERVERS`, set `MCP_REQUIRE_APPROVAL=false`:
then they act without asking, in runs and in chat. See
[Approvals](api-reference.md#approvals).

For example, this public server exposes LangChain documentation tools:

```dotenv
MCP_SERVERS='{"docs":{"transport":"streamable_http","url":"https://docs.langchain.com/mcp"}}'
```

A local open-source MCP server can use stdio. For example, the [MCP filesystem
server](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md)
requires Node.js and an explicit directory grant:

```dotenv
MCP_SERVERS='{"files":{"transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/absolute/allowed/path"]}}'
```

Put several named entries in the same JSON object to load all their tools.
HTTP entries may include a `headers` object; stdio entries may include `env`
for credentials. Keep secrets in the ignored `backend/.env`. Configure only
servers and filesystem paths that all authenticated AIMIx users may access; MCP server
credentials are shared by the backend. MCP discovery and calls have an explicit
`MCP_TIMEOUT_SECONDS` limit (30 seconds by default), and the full agent has
`AGENT_TIMEOUT_SECONDS` (one hour) and `AGENT_RECURSION_LIMIT` (25). MCP and
tool calls are never retried automatically; only model calls are, under
`LLM_MAX_RETRIES` (see [the retry policy](llm-providers.md#retry-policy)). The
selected model must support tool calling.

Each user can also connect **their own** MCP servers on the Settings page
(**Integrations**): a name, the server URL, and headers such as
`Authorization: Bearer …`. Their tools serve only that user's agents, named
`<name>_<tool>`; **Test connection** lists them. These servers must use
`https` and a public address. To try one running on your machine, set
`APP_ENV=local` and `INTEGRATIONS_ALLOW_PRIVATE_NETWORK=true` in `backend/.env`;
then `http://127.0.0.1:<port>/mcp` is accepted. Each integration has an **Ask me
before its tools act** switch, on by default: in a run, its tools wait for your
approval, and chat is not offered them. Switch it off for an integration you
trust to let its tools act at once, in runs and in chat.

After starting the backend, `GET /api/agent-tools` lists each pipeline tool's
name, description, and source (`AIMIx`, `MCP`, or the integration's name). The builder uses this list to
offer tool choices. Give a step an **Agent role** and choose **All tools**, **No
tools**, or exact named tools. All tools is the default for older pipelines;
the two native pipeline tools are `list_pipelines` and `inspect_pipeline`.
An explicit tool list fails at run time if one of its names is no longer
available. Built-in tools act without an approval prompt unless
`AGENT_APPROVAL_TOOLS` names them (for example
`AGENT_APPROVAL_TOOLS=save_artifact`); a request nobody answers within
`APPROVAL_TIMEOUT_SECONDS` (30 minutes) counts as declined.

### Coming from the Django version

Your old data lives in `backend/db.sqlite3`. Copy it into the new database once:

```bash
make migrate
make import-django-db     # accounts (same passwords), pipelines and steps
```

The import keeps ids and refuses to run into a database that already has
accounts, so running it twice is harmless. `db.sqlite3` is only read.

## Running

```bash
make run-aimix        # backend :8000 and frontend :4200 in parallel
```

Open <http://localhost:4200> and register an account: you are signed in at once and land on Missions.

- The Vite dev server **proxies `/api` to `http://127.0.0.1:8000`**
  (`frontend/vite.config.ts`), so the browser sees one origin and no CORS setup
  is needed in development.
- Interactive API docs (Swagger UI): <http://127.0.0.1:8000/api/docs>.
- Create an account from the terminal with `make create-user USERNAME=alice`.
- Stop everything with `make kill-all`.

Run one side only with `make run-backend` or `make run-frontend`.
The backend start target applies pending database migrations before launching the API.

## Try each feature

Signing in lands on **Missions**, the front door. The other screens are the same
features one step closer to the machinery.

1. **Missions** (`/mission`) — say what you want done, e.g. "Research the three main
competitors of my product and write a one-page comparison". AIMIx puts a team of
agents together and tells you in plain words who does what, which tools each one
uses and what you will need to provide; nothing is saved yet. Ask for changes in
your own words ("add an agent that checks the facts"), read the proposed changes
and **Apply** or **Discard** them. Press **Run it** (or type "run it"), fill in
what the team needs (you can attach a document) and the run starts; the first run
saves the mission. The team in the middle shows each agent waiting, running or
done and opens a side drawer to edit its role, prompt, model and tools; **Results**
leads with the deliverables, folds the full run details away once the run is done
and lists your newest files. Reopen a mission at `/mission/<id>` or with **Open in
mission view** on the builder, and hand it to the advanced mode with **Open in
builder**. Under 1280px wide the three panes become tabs. The conversation is kept
for the browser tab only; the team and its runs are saved on the server. Template
quick-starts sit under the examples on the empty screen.
2. **Chat** (`/chat`) — type a prompt; the LangGraph agent can use native pipeline functions and the configured MCP tools that need no approval (see [above](#give-chat-and-pipeline-steps-mcp-tools)).
3. **Pipeline Builder** (`/pipeline`) — use the workflow canvas to add parallel
   steps or insert a new stage. Give each step a role, prompt, model, and tool
   access; mark deliverables as **Output**. Write prompts using `{input}`,
   **Save**, then **Run** with an input. The run executes in the background:
   the diagram shows each step waiting, running, done or failed, outputs appear
   as soon as each step finishes, and **Stop** / **Resume** act on it. Run
   results group deliverables by stage and show each called tool's name and
   success/error status. You can leave the page; reopening the pipeline shows
   its latest run. To change a
   pipeline in a sentence, open **Ask AIMIx to change this pipeline** (e.g.
   "add an SEO agent that works alongside the marketing agent"), review the
   proposed changes and **Apply** them; nothing is saved until you save. A saved
   pipeline has **Open in mission view** to see it as a mission.
4. **Auto Pipeline** (`/auto-pipeline`) — describe a workflow in plain language;
   name the deliverables you want. The planner sees the available tools and
   proposes a role and tool list for each step. Review the generated stages and
   tool choices, refine them in a sentence if needed, then save and open the
   builder.
5. **Templates** (`/templates`) — pick one of eight ready-made missions (market
   research, competitor analysis, document digest, meeting actions, data
   insights, SEO brief, content calendar, launch plan). It opens in the builder
   as your own pipeline, on your default model and with only the tools you
   have; fill in its inputs and run it.
6. **Runs** (`/runs`, the **Runs** tab next to the pipeline screens) — every
   run, newest first, with its status, start and duration. Open one to follow
   it live, resume it where it stopped (finished steps are kept), or delete it.

## Talking to the API directly

```bash
# 1. get a token
curl -s -X POST localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"me","password":"secret-pass-123"}'

# 2. use it
TOKEN=...   # the "access" value from step 1
curl -s localhost:8000/api/models -H "Authorization: Bearer $TOKEN"
```

See [api-reference.md](api-reference.md) for every endpoint.

## Environments

`APP_ENV` selects the behaviour; everything else comes from the same variables.

| `APP_ENV` | Used by | Behaviour |
|---|---|---|
| `local` (default) | `make run-backend` | Throwaway `SECRET_KEY` allowed, `/api/docs` on |
| `test` | `pytest` (pinned in `tests/conftest.py`) | In-memory SQLite, no provider keys, fast hashing |
| `production` | your deployment | Refuses to start with `DEBUG=true`, no `SECRET_KEY`, or empty `ALLOWED_HOSTS`; HSTS on, `/api/docs` off |

In production run Uvicorn behind a TLS-terminating proxy that also redirects
HTTP to HTTPS, e.g. `uvicorn api.main:create_app --factory --proxy-headers`.
The `Dockerfile` does this for you; see [deployment.md](deployment.md) for the
image, CI and Railway.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `provider_not_configured` (503) | No key for your provider, either on the Settings page or in `backend/.env` (or it is still a placeholder) | Add one on the Settings page, or set it in `backend/.env` and restart the backend |
| `provider_not_configured` "can no longer be read" | `SECRET_KEY` changed after you saved a key | Enter the key again on the Settings page |
| `provider_unavailable` (502) | Provider rejected the call (bad key, unknown model, quota), or stayed overloaded through every retry (`llm.retry` warnings in the backend log) | Run `make run-llm`, then `cd backend && uv run python -m api.cli llm-probe "hi"` to see the provider's message |
| `provider_timeout` (504) | Model slower than `LLM_TIMEOUT_SECONDS` | Raise it in `.env`, or pick a faster model |
| Redirected to `/login` unexpectedly | Your session ended: it renews itself while the refresh cookie is valid (`JWT_REFRESH_DAYS`, 1 day by default), and a new `SECRET_KEY` ends every session | Sign in again |
| `no such table: users` / `pipelines` | Migrations not applied | `make migrate` |
| Frontend shows "Could not reach the server." | Backend not running on :8000 | `make run-backend` |
| Port already in use | A previous run is still alive | `make kill-all` |
| `validation_error` "Unknown model ..." | Model id in no provider's catalogue | Pick one from `GET /api/models`, or add it — see [llm-providers.md](llm-providers.md) |

# Deployment and CI

AIMIx ships as **one container**: the `Dockerfile` builds the React bundle,
then a Python image whose FastAPI process serves both `/api` and the app
(`api/frontend.py`, enabled by `FRONTEND_DIST_DIR`). One service, one origin:
no CORS and no backend URL in the bundle — the same arrangement the Vite dev
proxy gives you locally.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and every push to `main`:

| Job | What it does |
|---|---|
| `check` | `uv sync --frozen`, `npm ci`, then **`make check`** — Ruff, mypy, pytest (including the migrations-match-models check), Vitest and the production build. The same command you run locally (AGENTS.md §9). |
| `image` | Builds the `Dockerfile` and smoke-tests the container: `/api/health` answers and `/settings` returns the app shell. |

Railway deploys `main` only once both jobs pass (see *Wait for CI* below).

## The image

| | |
|---|---|
| Build | `docker build -t aimix .` |
| Runs as | non-root user `aimix` (uid 10001) |
| Start | `alembic upgrade head`, then Uvicorn on `$PORT` (default 8000) with proxy headers |
| Defaults | `APP_ENV=production`, `FRONTEND_DIST_DIR=/app/frontend/dist`, `DATABASE_URL=sqlite:////data/aimix.sqlite3`, `AGENT_WORKSPACE_DIR=/data/workspace`, `OMP_THREAD_LIMIT=1` |
| OCR | Tesseract 5 from Debian (`tesseract-ocr`, with `tesseract-ocr-eng` and `tesseract-ocr-fra`), for scanned PDFs and images. About 105 MB of the image |
| System packages | `fonts-dejavu-core` (installed with `--no-install-recommends`), the TrueType font PDF artifacts embed (`PDF_FONT_PATH`, `PDF_BOLD_FONT_PATH`) |
| Never contains | `backend/.env`, any `*.sqlite3`, tests, `node_modules` (`.dockerignore`) |

### OCR in the image

Uploaded images and PDF pages without a text layer are read by Tesseract (see
[api-reference.md](api-reference.md#documents)). The image installs English and
French, the default `DOCUMENT_OCR_LANGUAGES=eng+fra`. Another language needs its
`tesseract-ocr-<code>` package added to the `apt-get install` line in the
`Dockerfile`, and its code in `DOCUMENT_OCR_LANGUAGES`. At startup the app logs
one line saying whether OCR is ready (`documents.ocr status=ready`), turned off,
or unavailable and why (`binary_missing`, `languages_missing:<codes>`); while it
is unavailable, images are refused and scanned PDF pages are skipped, with a
message that says so.

| Variable | Default | Meaning |
|---|---|---|
| `DOCUMENT_OCR_ENABLED` | `true` | `false` turns OCR off |
| `DOCUMENT_OCR_LANGUAGES` | `eng+fra` | Tesseract codes joined by `+` |
| `DOCUMENT_OCR_MAX_PAGES` | `30` | Pages one document may send to OCR |
| `DOCUMENT_OCR_TIMEOUT_SECONDS` | `15` | Per page; a slower page is skipped |
| `DOCUMENT_OCR_DPI` | `300` | Resolution a PDF page is rendered at for OCR |
| `DOCUMENT_MAX_IMAGE_PIXELS` | `40000000` | Larger images are refused before decoding |

Each OCR'd page runs one `tesseract` process on one thread (`OMP_THREAD_LIMIT=1`:
more threads made no page faster, and under a one-CPU quota made each about 3.5
times slower). Expect about three seconds per dense A4 page per CPU, so a 30-page
scan holds its request for one to two minutes.

Try it locally — production settings refuse to start without these two:

```bash
docker run --rm -p 8080:8000 -v aimix-data:/data \
  -e SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
  -e ALLOWED_HOSTS=localhost -e ALLOW_PUBLIC_REGISTRATION=true aimix
# open http://localhost:8080, register, then add your key on the Settings page
```

## Railway

`railway.json` holds the build and deploy settings as code: Dockerfile build,
health check on `/api/health`, restart on failure, and rebuilds only when
application files change.

### One-time setup

1. **Project and service.** In Railway, *New Project → Deploy from GitHub repo →
   `AIMIx`* (or `railway init` then `railway up` from the CLI).
2. **Volume.** Add a volume to the service mounted at **`/data`** — the SQLite
   database and every user's files (`/data/workspace/user-<id>`: uploads and
   agent artifacts) live there. Without it every deploy starts from an empty
   database and loses the files. Size it for your users: each may keep up to
   `WORKSPACE_MAX_TOTAL_BYTES` (100 MB by default), so 50 active users can fill
   5 GB.
3. **Variables** (service → *Variables*):

   | Variable | Value | Why |
   |---|---|---|
   | `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` | Signs JWTs and encrypts saved API keys. Changing it signs everyone out and makes saved keys unreadable. |
   | `ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app` | Railway's health check calls with host `healthcheck.railway.app`; without it the deploy never turns healthy. |
   | `CORS_ALLOWED_ORIGINS` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | Same origin, so only for completeness. |
   | `ALLOW_PUBLIC_REGISTRATION` | `true` or unset | Off by default: without it `POST /api/register` answers `403` and nobody new can sign up. Set `true` for open sign-up; leave it unset to create accounts yourself (`python -m api.cli create-user NAME` in the service shell). Existing accounts are unaffected. |
   | `RAILWAY_RUN_UID` | `0` | Railway mounts volumes as root; the non-root image user could not write the database otherwise. |
   | `RUN_DEFAULT_MAX_COST_USD` | optional (default empty: no limit) | A spending limit, in US dollars, for every run whose starter sets none: the run stops, failed, once its model calls have cost this much. A user can set a different limit on any run, higher or lower, and raise it to resume a run that stopped; see [Spending limits](#spending-limits-and-usage). |
   | `WORKSPACE_MAX_TOTAL_BYTES` | optional (default `100000000`) | The storage limit of one user's files. Uploads (each capped at `DOCUMENT_MAX_BYTES`, 10 MB) and agent artifacts both count. |
   | `WORKSPACE_UPLOAD_EXTENSIONS` | optional | The file types the Files page accepts (default `.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.yaml,.yml,.html`). Downloads are always attachments, so allowing more types does not let them run in the app. |

4. **Domain.** *Settings → Networking → Generate Domain*.
5. **Wait for CI.** *Settings → Source*: connect the GitHub repo on branch
   `main` and enable **Wait for CI**, so a push deploys only after the CI
   workflow passes.

### Do not put LLM keys in Railway variables

If you set `ALLOW_PUBLIC_REGISTRATION=true`, registration is open. A server-wide
`OPEN_ROUTER_KEY` or `TOGAI_API_KEY` would let **anyone who registers** spend it. Leave them unset: each user saves their
own key on the Settings page, encrypted with `SECRET_KEY`.

### Users' integrations (their own MCP servers)

On the Settings page each user can connect MCP servers of their own; the
server then opens connections to addresses users choose. The guard, in
`api/services/addresses.py` and `api/services/integrations/`:

- **Streamable HTTP over `https` only**, never stdio (which would run a command
  in the container). Plain `http` is accepted only with `APP_ENV=local`.
- **Public addresses only.** The host must resolve to global addresses alone —
  never loopback, private, link-local (the cloud metadata address
  `169.254.169.254` included), shared or reserved — when the integration is
  saved, before a connection test, and before every request agents send. The
  MCP client follows redirects only within the same origin, and checks that
  request too. httpx resolves the name once more when it connects, so a DNS
  server that changes its answer within those milliseconds (DNS rebinding) can
  still slip through; this is the same residual risk as the `fetch_url` tool.
- **Leave `INTEGRATIONS_ALLOW_PRIVATE_NETWORK` unset.** It exists for local
  development only; the container refuses to start with it on in production.
- **Header values** (API keys, tokens) are encrypted with `SECRET_KEY` and never
  sent back to the browser. Changing `SECRET_KEY` makes them unreadable: the
  integration is skipped until its owner enters them again. The URL itself is
  stored as entered, so users should put tokens in headers, not in the URL.
- **Bounded:** `INTEGRATIONS_MAX_PER_USER` (10) per account, and every
  connection, test and tool call by `MCP_TIMEOUT_SECONDS`. Setting the limit to
  `0` stops new integrations being added; existing ones keep working until
  their owners delete or switch them off.
- **Isolation:** an integration serves only its owner's agents. Its tool
  results enter that user's agent context like any tool output, so a server a
  user connects can steer that user's agents — with that user's tools and data
  only.
- **Logs** never contain integration URLs or header values: the app logs ids,
  names and failure kinds, and keeps the `httpx` and `mcp` loggers at `WARNING`
  because they would log each request's URL.

If the platform restricts outbound traffic, allow `https` to the services your
users connect.

### Optional: let agents run code (`E2B_API_KEY`)

`run_python` lets agents run Python for data analysis and charts. It is
optional: without `E2B_API_KEY` the tool is simply not offered and everything
else works. Railway gives the container no Docker socket, and AIMIx never runs
agent code in its own process anyway: each call starts a fresh
[E2B](https://e2b.dev) cloud sandbox with no internet access, which is
destroyed when the call ends and lives at most `SANDBOX_TIMEOUT_SECONDS`
(60 by default).

What E2B receives: the code the agent writes, which can embed anything in the
agent's context (the run's inputs, earlier tool results), and the workspace
files it names in `input_files` (at most `SANDBOX_MAX_FILES`, each within
`WORKSPACE_MAX_FILE_BYTES`). What comes back: the output, the files the code
writes to `/home/user/outputs/` and the charts it displays, saved to the
user's workspace under `sandbox/<UTC time>/`. AIMIx sends nothing else: no
database content and no credential but the E2B key itself.

The key is server-wide, like a server-wide LLM key: every user who can run
agents spends it, and with `ALLOW_PUBLIC_REGISTRATION=true` that is anyone who
registers. Each call is bounded by `SANDBOX_TIMEOUT_SECONDS` of sandbox time;
set the key only if you accept that cost, and watch the usage in your E2B
account.

### Spending limits and usage

Every pipeline run records the tokens its model calls used and, where it can be
known, what they cost; users see it on the Runs screen and under Settings →
Usage (the last 30 days). Where the cost comes from is in
[LLM providers](llm-providers.md#usage-and-cost): OpenRouter reports it with each
answer, TogetherAI is priced from the catalogue, and a model with no known price
shows its tokens and "Cost unknown for this model".

A run can carry a limit and is stopped *while it runs* once its calls reach it
(`409 budget_exceeded` over the API; the run ends `failed`, its finished steps
kept). `RUN_DEFAULT_MAX_COST_USD` is the limit of a run that sets none; it is the
operator's guard against a runaway agent loop, and the one thing capping what
users spend when you provide the model key. Users who bring their own key (the
setup recommended above) spend their own money, so the default is optional.
Things to know:

- The limit only counts costs the app knows. A model with an unknown cost counts
  for tokens only, so a cost limit never stops it (a token limit set through the
  API does).
- A call in flight when the limit is reached still finishes and is counted, so a
  run can pass its limit by the calls then running (at most one per parallel
  step).
- The usage report counts pipeline runs only, not chat messages.
- Runs recorded before this feature existed show no usage ("No usage
  recorded"); the migration (`d51cc5c2111e`) adds its columns in place and keeps
  every run and step.

### Limits of this setup

- **One replica.** SQLite on a volume supports a single instance; do not scale
  the service out. Moving to Postgres needs a driver (e.g. `psycopg`) and a
  `postgresql+psycopg://` `DATABASE_URL`, and is not covered by the test suite.
- **Brief downtime on deploy.** Railway stops the old container before starting
  the new one when a volume is attached.
- **A redeploy interrupts the runs in progress.** Pipeline runs execute in the
  API process. On shutdown each active run is marked *interrupted* (within
  `RUN_SHUTDOWN_GRACE_SECONDS`, default 5, well inside the platform's stop
  timeout); after a crash or a hard kill, the next start marks them instead.
  The steps they finished are kept, and **Resume** on the Runs screen (or
  `POST /api/runs/<id>/resume`) continues each one where it stopped. Runs still
  waiting for a slot are interrupted the same way.
- **One Uvicorn worker.** Runs are queued per process (at most
  `RUN_MAX_CONCURRENT` at once). The image starts a single worker; do not add
  `--workers`, or a starting worker would mark the runs of the others as
  interrupted.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Deploy stuck on "healthcheck failed", logs show `400` | `healthcheck.railway.app` missing from `ALLOWED_HOSTS` | Add it |
| Container exits: `SECRET_KEY must be set in production` | Variable missing | Set `SECRET_KEY` |
| `sqlite3.OperationalError: unable to open database file` | No volume at `/data`, or `RAILWAY_RUN_UID` unset | Mount the volume at `/data`; set `RAILWAY_RUN_UID=0` |
| Everyone signed out and saved keys "can no longer be read" | `SECRET_KEY` changed | Keep it stable; users re-enter keys in Settings |
| Container exits: `FRONTEND_DIST_DIR=… has no index.html` | Image built without the frontend stage | Build with the repository `Dockerfile` |
| Container exits: `INTEGRATIONS_ALLOW_PRIVATE_NETWORK must be false in production` | A local-development setting reached production | Remove the variable |
| An integration test says "… is not a public address" | The MCP server's host resolves to a private or internal address | Integrations only reach public `https` servers; publish the server on a public address |
| Images refused with "images need OCR, which is not available"; log shows `documents.ocr status=unavailable` | Tesseract or a language in `DOCUMENT_OCR_LANGUAGES` is not installed, or `DOCUMENT_OCR_ENABLED=false` | Build with the repository `Dockerfile`; install the `tesseract-ocr-<code>` package for each language, or remove the code |
| Files vanish after a deploy | No volume at `/data` (files live in `/data/workspace`) | Mount the volume at `/data` |
| Uploads answer `storage_quota_exceeded` | That user's files reached `WORKSPACE_MAX_TOTAL_BYTES` | They delete files on the Files page, or raise the limit |
| PDFs show boxes instead of letters; log has `artifacts.pdf_font_unavailable` | No TrueType font at `PDF_FONT_PATH` (image built without `fonts-dejavu-core`, or a custom path) | Build with the repository `Dockerfile`, or point `PDF_FONT_PATH` / `PDF_BOLD_FONT_PATH` at a font that covers your users' scripts |
| Runs stop with "Spending limit reached" | The run's limit, or `RUN_DEFAULT_MAX_COST_USD` for a run with none, was reached | Raise the limit when resuming the run (Runs screen, or `POST /api/runs/<id>/resume` with `max_cost_usd`), or raise or unset the variable |
| Runs show *Interrupted* after a deploy | The process stopped while they ran (logged as `run.finished … status=interrupted` or `run.interrupted_on_startup`) | Resume them from the Runs screen; finished steps are kept |

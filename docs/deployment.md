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
| `audit` | Known vulnerabilities in the locked dependencies: `pip-audit` over the Python packages the image installs, `npm audit --audit-level=high` over the frontend lockfile (see [Dependency updates and audits](#dependency-updates-and-audits)). |
| `image` | Builds the `Dockerfile` and smoke-tests the container twice. Started as root on a root-owned volume, as on Railway: `/api/health` answers, `/settings` returns the app shell, the server runs as uid 10001 and owns the database it created. Started with `--user 10001`: it serves as well. |

Railway deploys `main` only once all three jobs pass (see *Wait for CI* below).

### Dependency updates and audits

- **Pinned.** The `Dockerfile` pins each base image by digest
  (`node:24-alpine@sha256:…`, the tag kept for readers) and `ci.yml` pins each
  action to a commit (`actions/checkout@<sha> # v7.0.1`); `uv.lock` and
  `package-lock.json` pin the packages. A tag that moves changes nothing until a
  pull request says so. The Debian packages (`apt-get install`) come from the
  base image's Debian release when the image is built.
- **Updated weekly by Dependabot** (`.github/dependabot.yml`): GitHub Actions,
  the base images, npm (`frontend/`) and uv (`uv.lock`). Minor and patch updates
  come as one pull request per ecosystem; a major update comes on its own, as
  does SQLAlchemy, which `pyproject.toml` keeps below 2.1 until the code moves to
  2.1's typing. Dependabot does not change the Python or Node version: move the
  `python:` image tag together with `.python-version` (which CI and the
  `uv sync` in the image read), and `node:` with `node-version` in `ci.yml`.
- **Audited on every pull request and push** (the `audit` job). Python:
  `uv export --frozen --no-dev` lists the packages the image installs at their
  locked versions, and a pinned `pip-audit` looks each one up; the dev tools
  (Ruff, mypy, pytest) only run in CI and are left out. npm:
  `npm audit --audit-level=high` over the whole lockfile, dev dependencies
  included, because Vite, Rollup and esbuild build the bundle browsers run; only
  high and critical advisories fail the job (a known-malicious package is rated
  critical).
- **When the audit fails, `main` does not deploy.** Update the package (take the
  Dependabot pull request, or `uv lock --upgrade-package NAME`, or
  `npm update NAME --prefix frontend`). When no fixed version exists and the
  advisory does not apply, add `--ignore-vuln <ID>` to the `pip-audit` line, or
  for npm pin a fixed transitive version with `overrides` in
  `frontend/package.json`, and say why in the commit.
- Turn on Dependabot alerts and security updates in the repository's
  *Settings → Code security*, so advisories published between pushes reach you.

## The image

| | |
|---|---|
| Build | `docker build -t aimix .` |
| Base images | `python:3.12-slim-trixie` (Python 3.12, as in `.python-version`), `node:24-alpine` for the bundle and `ghcr.io/astral-sh/uv` to install the locked dependencies, each pinned by digest |
| Runs as | non-root user `aimix` (uid 10001). The entrypoint (`docker-entrypoint.sh`) starts as root only to give `aimix` the volume at `/data` (the mount point, and anything an earlier run as root left there), then drops to `aimix` with no capabilities and runs the command. Started as another user (`--user 10001`), it runs the command as it is |
| Start | `alembic upgrade head`, then Uvicorn on `$PORT` (default 8000); it reads proxy headers only when `TRUSTED_PROXY_HOPS` is above 0 (see [Client address behind a proxy](#client-address-behind-a-proxy)) |
| Defaults | `APP_ENV=production`, `FRONTEND_DIST_DIR=/app/frontend/dist`, `AIMIX_DATA_DIR=/data`, `DATABASE_URL=sqlite:////data/aimix.sqlite3`, `AGENT_WORKSPACE_DIR=/data/workspace`, `TRUSTED_PROXY_HOPS=2`, `FORWARDED_ALLOW_IPS=*`, `OMP_THREAD_LIMIT=1` |
| Health | `HEALTHCHECK` calls `/api/health` every 30 s, with the first `ALLOWED_HOSTS` entry as `Host` (Railway ignores it and uses `healthcheckPath`) |
| OCR | Tesseract 5 from Debian (`tesseract-ocr`, with `tesseract-ocr-eng` and `tesseract-ocr-fra`), for scanned PDFs and images. About 105 MB of the image |
| System packages | `fonts-dejavu-core` (installed with `--no-install-recommends`), the TrueType font PDF artifacts embed (`PDF_FONT_PATH`, `PDF_BOLD_FONT_PATH`) |
| Never contains | `uv`, `backend/.env`, users' files from a development checkout (`backend/workspace/`), any `*.sqlite3`, logs, tests, caches, `node_modules`: `.dockerignore` lets in only what the `Dockerfile` copies |

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
| `DOCUMENT_OCR_MAX_SECONDS` | `120` | All the OCR of one document; no page starts after it |
| `DOCUMENT_OCR_TIMEOUT_SECONDS` | `15` | Per page; a slower page is skipped |
| `DOCUMENT_MAX_CONCURRENT_EXTRACTIONS` | `2` | Documents read at once; another waits `DOCUMENT_EXTRACTION_WAIT_SECONDS` (`30`), then gets 503 |
| `DOCUMENT_OCR_DPI` | `300` | Resolution a PDF page is rendered at for OCR |
| `DOCUMENT_MAX_IMAGE_PIXELS` | `40000000` | Larger images are refused before decoding |

Each OCR'd page runs one `tesseract` process on one thread (`OMP_THREAD_LIMIT=1`:
more threads made no page faster, and under a one-CPU quota made each about 3.5
times slower). Expect about three seconds per dense A4 page per CPU, so a 30-page
scan holds its request for one to two minutes.

Try it locally — production settings refuse to start without these two (and
`SECRET_KEY` must be at least 32 characters). No proxy stands in front here, so
`TRUSTED_PROXY_HOPS=0`:

```bash
docker run --rm -p 8080:8000 -v aimix-data:/data \
  -e SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
  -e ALLOWED_HOSTS=localhost -e TRUSTED_PROXY_HOPS=0 -e ALLOW_PUBLIC_REGISTRATION=true aimix
# open http://localhost:8080, register, then add your key on the Settings page
```

### Client address behind a proxy

The login and registration rate limits count requests per client address. Behind
a proxy the connection comes from the proxy, so the app finds the client in the
`X-Forwarded-For` header instead, counting `TRUSTED_PROXY_HOPS` entries from the
right: the entries on the right are added by the proxies, while anything further
left may come from the client and can be forged. With no header the app uses the
connection's address; with fewer entries than hops, the leftmost one.

| Where the container runs | `TRUSTED_PROXY_HOPS` |
|---|---|
| Railway | `2`, the image's default |
| A plain `docker run`, no proxy in front | `0`, so the header is ignored |
| Behind one reverse proxy of your own (nginx, Caddy, a load balancer) | `1` |

Railway does not document how its edge proxy fills the header. A Railway user's
measurement (September 2026) found that the edge drops what the client sent and
hands the app two entries, the client and then a Railway or CDN hop; so the
client is the second entry from the right. `1` would read that shared hop and put
every user in one rate-limit bucket. `2` is right whether the edge drops the
client's entries or appends to them. Railway may change this, so check it on your
service: log in from two networks and see whether they are limited separately.
Requests that reach the service over Railway's private network
(`*.railway.internal`) skip the edge and its cleaning of the header; do not
expose the app there to anything you do not trust.

The same variable decides whether Uvicorn reads the proxy headers. Above 0 it
takes the scheme from `X-Forwarded-Proto`, which is how the app knows a request
came over https, from any address (`FORWARDED_ALLOW_IPS=*`, as the container is
reached only through the proxy). Uvicorn then also logs the leftmost
`X-Forwarded-For` entry as the client address in its access log, which the
client can forge, so nothing relies on it. At 0 Uvicorn ignores the proxy
headers.

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
   | `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` | Signs JWTs and encrypts saved API keys; at least 32 characters. Changing it signs everyone out and makes saved keys unreadable, unless the old key is kept in `SECRET_KEY_FALLBACKS`. |
   | `ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app` | Railway's health check calls with host `healthcheck.railway.app`; without it the deploy never turns healthy. |
   | `CORS_ALLOWED_ORIGINS` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | Same origin, so only for completeness. |
   | `ALLOW_PUBLIC_REGISTRATION` | `true` or unset | Off by default: without it `POST /api/register` answers `403` and nobody new can sign up. Set `true` for open sign-up; leave it unset to create accounts yourself (`docker-entrypoint.sh python -m api.cli create-user NAME` in the service shell, which runs it as the app user). Existing accounts are unaffected. |
   | `TRUSTED_PROXY_HOPS` | unset (the image sets `2`) | Where the rate limits find the client's address; see [Client address behind a proxy](#client-address-behind-a-proxy). |
   | `RUN_DEFAULT_MAX_COST_USD` | optional (default empty: no limit) | A spending limit, in US dollars, for every run whose starter sets none: the run stops, failed, once its model calls have cost this much. A user can set a different limit on any run, higher or lower, and raise it to resume a run that stopped; see [Spending limits](#spending-limits-and-usage). |
   | `WORKSPACE_MAX_TOTAL_BYTES` | optional (default `100000000`) | The storage limit of one user's files. Uploads (each capped at `DOCUMENT_MAX_BYTES`, 10 MB) and agent artifacts both count. |
   | `WORKSPACE_UPLOAD_EXTENSIONS` | optional | The file types the Files page accepts (default `.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.yaml,.yml,.html`). Downloads are always attachments, so allowing more types does not let them run in the app. |

   `RAILWAY_RUN_UID` is no longer needed: the image hands the root-owned volume
   to its own user by itself. A service that still sets it to `0` keeps working
   (the app still runs as uid 10001); you can delete the variable.

4. **Domain.** *Settings → Networking → Generate Domain*.
5. **Wait for CI.** *Settings → Source*: connect the GitHub repo on branch
   `main` and enable **Wait for CI**, so a push deploys only after the CI
   workflow passes.

### Do not put LLM keys in Railway variables

If you set `ALLOW_PUBLIC_REGISTRATION=true`, registration is open. A server-wide
`OPEN_ROUTER_KEY` or `TOGAI_API_KEY` is never used for accounts unless you also
set `ALLOW_SERVER_LLM_KEY=true`, which would let **anyone who registers** spend
it. Leave both unset: each user saves their own key on the Settings page,
encrypted with `SECRET_KEY`, and a request without one fails with
`provider_not_configured`.

### Users' integrations (their own MCP servers)

On the Settings page each user can connect MCP servers of their own; the
server then opens connections to addresses users choose. The guard, in
`api/services/addresses.py` and `api/services/integrations/`:

- **Streamable HTTP over `https` only**, never stdio (which would run a command
  in the container). Plain `http` is accepted only with `APP_ENV=local`.
- **Public addresses only.** The host must resolve to global addresses alone —
  never loopback, private, link-local (the cloud metadata address
  `169.254.169.254` included), shared or reserved — when the integration is
  saved, before a connection test, and on every connection agents open, which
  then goes to one of exactly the addresses that were checked: a DNS server
  that changes its answer (DNS rebinding) cannot redirect it, and proxy
  variables in the environment are ignored. The MCP client follows redirects
  only within the same origin, and checks that connection too. The
  `fetch_url` tool uses the same transport.
- **Leave `INTEGRATIONS_ALLOW_PRIVATE_NETWORK` unset.** It exists for local
  development only; the container refuses to start with it on in production.
- **Header values** (API keys, tokens) are encrypted with `SECRET_KEY` and never
  sent back to the browser. Changing `SECRET_KEY` makes them unreadable: the
  integration is skipped until its owner enters them again. The URL itself is
  stored as entered, so users should put tokens in headers, not in the URL.
- **Bounded:** `INTEGRATIONS_MAX_PER_USER` (10) per account, every
  connection, test and tool call by `MCP_TIMEOUT_SECONDS`, one response by
  `MCP_MAX_RESPONSE_BYTES` and a tool result's text by
  `MCP_TOOL_RESULT_MAX_CHARS`. Setting the limit to
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

### Approval gates: agents ask before acting on outside systems

An MCP tool can send an email or update a CRM, so in a pipeline run such a call
waits for the run's owner to approve it (the run shows *Waiting for you* and the
Runs page offers **Approve** and **Decline**). Settings, all optional:

| Variable | Default | Effect |
|---|---|---|
| `MCP_REQUIRE_APPROVAL` | `true` | The tools of `MCP_SERVERS` ask first. Set `false` only for servers whose tools are harmless to run unattended (read-only documentation, say) |
| `AGENT_APPROVAL_TOOLS` | empty | Comma-separated built-in tools that also ask first, for example `save_artifact,run_python` |
| `APPROVAL_TIMEOUT_SECONDS` | `1800` | A request nobody answers expires after this long and counts as declined; it is never longer than `AGENT_TIMEOUT_SECONDS` (3600), which the wait counts toward |
| `APPROVAL_POLL_SECONDS` | `1` | How often a waiting run reads the database for the answer |
| `APPROVAL_ARGUMENTS_MAX_CHARS` | `4000` | How much of a call's arguments the owner can read (long text values are shortened) |

Each user also has an **Ask me before its tools act** switch on every
integration (on by default, including integrations saved before it existed).

- **Chat does not get tools that ask.** A chat has no run to pause, so the
  tools that ask first are not offered to it; it can still start a pipeline run,
  whose steps ask. Operators who gave chat `MCP_SERVERS` tools must set
  `MCP_REQUIRE_APPROVAL=false` to keep them there, and each user must switch
  the integration's approval off to use it in chat.
- **A restart or redeploy expires the requests** of the runs it interrupts; a
  resumed run asks again. Requests are kept in the database and read by polling,
  so nothing depends on the process's memory.
- **Answers are the owner's alone.** Another account's run and requests answer
  `404`. The arguments a request shows are stored with it (so the owner can read
  what would happen), and never written to the logs: the app logs
  `approval.requested` and `approval.decided` with ids, the tool's name and the
  outcome.

### Optional: let agents search the web (`TAVILY_API_KEY`)

Agents can search the web (`web_search`, through [Tavily](https://tavily.com)) and
read public pages (`fetch_url`). Out of the box **neither is offered**, for two
separate reasons:

- `web_search` needs `TAVILY_API_KEY`. Without it the tool does not exist.
- Agents can also read the user's files (the Files page, `read_workspace_file`,
  `read_csv`...). A web page that tells the agent what to do (a prompt injection)
  could make it put a file's contents into a search query or a URL, which leaves
  the server. So whenever file-reading tools are offered, the two web tools are
  taken away, unless `AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS=true`.

To give agents the web, pick the trade-off you accept:

| Choice | Setting | What it means |
|---|---|---|
| Allow both (simple) | `TAVILY_API_KEY=...` and `AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS=true` | Agents search and fetch freely, and can also read files. Only for deployments where you trust what users make agents read |
| Allow, but ask first | the two settings above plus `AGENT_APPROVAL_TOOLS=web_search,fetch_url` | In a pipeline run each search or fetch waits for the owner's OK on the Runs screen. Chat is not offered tools that must ask, so it has no web |
| Web without files | `TAVILY_API_KEY=...` and a shorter `AGENT_BUILTIN_TOOLS` without `list_workspace_files`, `read_workspace_file`, `search_workspace_files`, `read_csv` and `run_python` | Agents search the web but cannot read stored files |

`fetch_url` only reaches public addresses (see [architecture.md](architecture.md#built-in-tools)).
Searches are sent to Tavily, which sees the query text, so they are covered by the
same trust decision as an LLM provider. Missions that research the market run on
the model's own knowledge until one of these is set; their prompts tell the
agents to mark figures as estimates.

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
registers. Each call is bounded by `SANDBOX_TIMEOUT_SECONDS` of sandbox time
and each account by `SANDBOX_MAX_CALLS_PER_HOUR` calls (120); set the key only
if you accept that cost, and watch the usage in your E2B account.

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

### Scheduled runs

Users can make a pipeline run by itself (the builder's *Schedule this pipeline*
panel, listed under *Runs → Schedules*). The scheduler is a thread **inside the
API process**: every `SCHEDULER_TICK_SECONDS` it starts the runs that are due, on
the same executor as manual runs, so `RUN_MAX_CONCURRENT` still bounds them and
the rest wait queued.

| Variable | Default | Meaning |
|---|---|---|
| `SCHEDULER_ENABLED` | `true` | `false` keeps every schedule saved and starts none. Use it on any process that is not *the* one scheduler |
| `SCHEDULER_TICK_SECONDS` | `30` | How often due schedules are looked for; a run starts at most this late |
| `SCHEDULES_MAX_PER_USER` | `20` | Schedules one account may have (`0` stops new ones; existing ones keep running until switched off or deleted) |

- **Single replica, like runs.** An occurrence is claimed with a compare-and-set
  on the schedule's `next_run_at`, so even two processes sharing a database never
  start the same occurrence. But the run executor still assumes one process (see
  below), so do not scale out; a second process, if you ever run one, needs
  `SCHEDULER_ENABLED=false`.
- **Nothing runs while the container is down.** A deploy stops the old container
  before it starts the new one. A schedule that came due meanwhile runs **once**
  when the app is back (within one tick), not once per missed time. A run that a
  redeploy interrupts is *Interrupted* and can be resumed, like any other.
- **Runs use the owner's own key.** Each scheduled run starts with its owner's LLM
  provider and key (the Settings page, else the server's); an account with none
  gets the reason on the schedule ("it could not start: No API key is set…") and
  no run, and the schedule waits for its next time. A schedule keeps spending that
  key (and `E2B_API_KEY`, if set, when its agents run code) until it is switched
  off or deleted; hourly is the shortest it can be, and `SCHEDULES_MAX_PER_USER`
  bounds how many an account has.
- **Time zones need tz data.** Schedules are read on an IANA time zone's clock
  (Python's `zoneinfo`), which finds its data in the system database or else in
  the `tzdata` Python package. The image installs that package (the lockfile
  pulls it in through `python-dateutil`, a dependency of the E2B client), and the
  Debian base normally has the system database as well. Remove both and no zone
  would be accepted ("Unknown time zone").
- **Logs** carry ids and outcomes only, never inputs or outputs:
  `scheduler.started`, `schedule.fired` (schedule, run and slot),
  `schedule.start_failed` (with the error code), `schedule.fire_crashed` and
  `scheduler.tick_failed` (with a traceback).

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
  waiting for a slot, or waiting for an approval, are interrupted the same way
  (their pending requests expire, and a resumed run asks again).
- **One Uvicorn worker.** Runs are queued per process (at most
  `RUN_MAX_CONCURRENT` at once), and each worker would run its own scheduler. The
  image starts a single worker; do not add `--workers`, or a starting worker would
  mark the runs of the others as interrupted.
- **Schedules fire only while the process is up** (see
  [Scheduled runs](#scheduled-runs)); a time missed during a deploy is run once
  afterwards, not replayed.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Deploy stuck on "healthcheck failed", logs show `400` | `healthcheck.railway.app` missing from `ALLOWED_HOSTS` | Add it |
| Container exits: `SECRET_KEY must be set in production` | Variable missing | Set `SECRET_KEY` |
| Container exits: `SECRET_KEY must be at least 32 characters in production` (or `must not be the local development key`) | A short or throwaway key | Generate one with `secrets.token_urlsafe(50)`; to keep sessions and saved keys, list the old one in `SECRET_KEY_FALLBACKS` ([rotating `SECRET_KEY`](backend.md#rotating-secret_key)) |
| Container exits: `PASSWORD_HASH_ITERATIONS must be at least 600000` | A low work factor reached production | Remove the variable (the default is 1,000,000) |
| `sqlite3.OperationalError: unable to open database file` | No volume at `/data`, or the container was started as a user other than root or 10001 (`--user`), so the entrypoint could not give it the volume | Mount the volume at `/data`; let the container start as root (the default), or make the volume owned by 10001 |
| Container exits at start: `chown: changing ownership of '/data…': Operation not permitted` | The runtime refused root's `chown` on the volume (a rootless runtime, or a network filesystem that squashes root) | Make the volume owned by uid 10001 and start with `--user 10001` |
| One user's failed logins rate-limit everyone, or a client dodges the limit by sending its own `X-Forwarded-For` | `TRUSTED_PROXY_HOPS` does not match the proxies in front | Set it as in [Client address behind a proxy](#client-address-behind-a-proxy) |
| Everyone signed out and saved keys "can no longer be read" | `SECRET_KEY` changed | Put the previous key in `SECRET_KEY_FALLBACKS` ([rotating `SECRET_KEY`](backend.md#rotating-secret_key)); without it, users re-enter keys in Settings |
| Container exits: `FRONTEND_DIST_DIR=… has no index.html` | Image built without the frontend stage | Build with the repository `Dockerfile` |
| Container exits: `INTEGRATIONS_ALLOW_PRIVATE_NETWORK must be false in production` | A local-development setting reached production | Remove the variable |
| An integration test says "… is not a public address" | The MCP server's host resolves to a private or internal address | Integrations only reach public `https` servers; publish the server on a public address |
| Images refused with "images need OCR, which is not available"; log shows `documents.ocr status=unavailable` | Tesseract or a language in `DOCUMENT_OCR_LANGUAGES` is not installed, or `DOCUMENT_OCR_ENABLED=false` | Build with the repository `Dockerfile`; install the `tesseract-ocr-<code>` package for each language, or remove the code |
| Files vanish after a deploy | No volume at `/data` (files live in `/data/workspace`) | Mount the volume at `/data` |
| Uploads answer `storage_quota_exceeded` | That user's files reached `WORKSPACE_MAX_TOTAL_BYTES` | They delete files on the Files page, or raise the limit |
| PDFs show boxes instead of letters; log has `artifacts.pdf_font_unavailable` | No TrueType font at `PDF_FONT_PATH` (image built without `fonts-dejavu-core`, or a custom path) | Build with the repository `Dockerfile`, or point `PDF_FONT_PATH` / `PDF_BOLD_FONT_PATH` at a font that covers your users' scripts |
| Runs stop with "Spending limit reached" | The run's limit, or `RUN_DEFAULT_MAX_COST_USD` for a run with none, was reached | Raise the limit when resuming the run (Runs screen, or `POST /api/runs/<id>/resume` with `max_cost_usd`), or raise or unset the variable |
| Runs show *Interrupted* after a deploy | The process stopped while they ran (logged as `run.finished … status=interrupted` or `run.interrupted_on_startup`) | Resume them from the Runs screen; finished steps are kept |
| A schedule never runs; no `scheduler.started` line in the log | `SCHEDULER_ENABLED=false`, or the schedule is off (its "Next run" says so) | Remove the variable; switch the schedule on |
| A schedule says "it could not start: No API key is set for …" | Its owner saved no key and the server has none | The owner adds a key on the Settings page; the schedule's next time starts normally |
| Creating a schedule fails with "Unknown time zone" for every zone | The image has no time zone database | Build with the repository `Dockerfile`, or install `tzdata` |

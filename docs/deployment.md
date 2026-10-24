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
| Defaults | `APP_ENV=production`, `FRONTEND_DIST_DIR=/app/frontend/dist`, `DATABASE_URL=sqlite:////data/aimix.sqlite3` |
| Never contains | `backend/.env`, any `*.sqlite3`, tests, `node_modules` (`.dockerignore`) |

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
   database lives there. Without it every deploy starts from an empty database.
3. **Variables** (service → *Variables*):

   | Variable | Value | Why |
   |---|---|---|
   | `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` | Signs JWTs and encrypts saved API keys. Changing it signs everyone out and makes saved keys unreadable. |
   | `ALLOWED_HOSTS` | `${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app` | Railway's health check calls with host `healthcheck.railway.app`; without it the deploy never turns healthy. |
   | `CORS_ALLOWED_ORIGINS` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | Same origin, so only for completeness. |
   | `ALLOW_PUBLIC_REGISTRATION` | `true` or unset | Off by default: without it `POST /api/register` answers `403` and nobody new can sign up. Set `true` for open sign-up; leave it unset to create accounts yourself (`python -m api.cli create-user NAME` in the service shell). Existing accounts are unaffected. |
   | `RAILWAY_RUN_UID` | `0` | Railway mounts volumes as root; the non-root image user could not write the database otherwise. |

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

### Limits of this setup

- **One replica.** SQLite on a volume supports a single instance; do not scale
  the service out. Moving to Postgres needs a driver (e.g. `psycopg`) and a
  `postgresql+psycopg://` `DATABASE_URL`, and is not covered by the test suite.
- **Brief downtime on deploy.** Railway stops the old container before starting
  the new one when a volume is attached.

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

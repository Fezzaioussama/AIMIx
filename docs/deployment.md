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
  -e ALLOWED_HOSTS=localhost aimix
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
   | `RAILWAY_RUN_UID` | `0` | Railway mounts volumes as root; the non-root image user could not write the database otherwise. |

4. **Domain.** *Settings → Networking → Generate Domain*.
5. **Wait for CI.** *Settings → Source*: connect the GitHub repo on branch
   `main` and enable **Wait for CI**, so a push deploys only after the CI
   workflow passes.

### Do not put LLM keys in Railway variables

Registration is open. A server-wide `OPEN_ROUTER_KEY` or `TOGAI_API_KEY` would
let **anyone who registers** spend it. Leave them unset: each user saves their
own key on the Settings page, encrypted with `SECRET_KEY`.

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

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
| Defaults | `APP_ENV=production`, `FRONTEND_DIST_DIR=/app/frontend/dist`, `DATABASE_URL=sqlite:////data/aimix.sqlite3`, `AGENT_WORKSPACE_DIR=/data/workspace` |
| System packages | `fonts-dejavu-core` (installed with `--no-install-recommends`), the TrueType font PDF artifacts embed (`PDF_FONT_PATH`, `PDF_BOLD_FONT_PATH`) |
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
   | `WORKSPACE_MAX_TOTAL_BYTES` | optional (default `100000000`) | The storage limit of one user's files. Uploads (each capped at `DOCUMENT_MAX_BYTES`, 10 MB) and agent artifacts both count. |
   | `WORKSPACE_UPLOAD_EXTENSIONS` | optional | The file types the Files page accepts (default `.pdf,.docx,.txt,.md,.csv,.json,.yaml,.yml,.html`). Downloads are always attachments, so allowing more types does not let them run in the app. |

4. **Domain.** *Settings → Networking → Generate Domain*.
5. **Wait for CI.** *Settings → Source*: connect the GitHub repo on branch
   `main` and enable **Wait for CI**, so a push deploys only after the CI
   workflow passes.

### Do not put LLM keys in Railway variables

If you set `ALLOW_PUBLIC_REGISTRATION=true`, registration is open. A server-wide
`OPEN_ROUTER_KEY` or `TOGAI_API_KEY` would let **anyone who registers** spend it. Leave them unset: each user saves their
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
| Files vanish after a deploy | No volume at `/data` (files live in `/data/workspace`) | Mount the volume at `/data` |
| Uploads answer `storage_quota_exceeded` | That user's files reached `WORKSPACE_MAX_TOTAL_BYTES` | They delete files on the Files page, or raise the limit |
| PDFs show boxes instead of letters; log has `artifacts.pdf_font_unavailable` | No TrueType font at `PDF_FONT_PATH` (image built without `fonts-dejavu-core`, or a custom path) | Build with the repository `Dockerfile`, or point `PDF_FONT_PATH` / `PDF_BOLD_FONT_PATH` at a font that covers your users' scripts |

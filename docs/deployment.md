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
| Defaults | `APP_ENV=production`, `FRONTEND_DIST_DIR=/app/frontend/dist`, `DATABASE_URL=sqlite:////data/aimix.sqlite3`, `OMP_THREAD_LIMIT=1` |
| OCR | Tesseract 5 from Debian (`tesseract-ocr`, with `tesseract-ocr-eng` and `tesseract-ocr-fra`), for scanned PDFs and images. About 105 MB of the image |
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
| Images refused with "images need OCR, which is not available"; log shows `documents.ocr status=unavailable` | Tesseract or a language in `DOCUMENT_OCR_LANGUAGES` is not installed, or `DOCUMENT_OCR_ENABLED=false` | Build with the repository `Dockerfile`; install the `tesseract-ocr-<code>` package for each language, or remove the code |

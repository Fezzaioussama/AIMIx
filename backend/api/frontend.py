"""Serves the built React app from the API process — wiring only, no logic.

With FRONTEND_DIST_DIR set (the production image sets it), one service answers
both /api and the single-page app on one origin: no CORS, and no backend URL in
the bundle. In development the Vite dev server plays this part instead.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from api.exceptions import NotFound
from api.routes import API_PREFIX

INDEX = "index.html"
#: Vite content-hashes everything under assets/, so those files never change.
#: index.html names the current hashes and must be revalidated on every load,
#: or a browser would keep requesting a previous deploy's bundle.
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
REVALIDATE = {"Cache-Control": "no-cache"}


def install_frontend(app: FastAPI, dist_dir: str) -> None:
    """Serve ``dist_dir`` at ``/``, falling back to index.html for client routes."""
    if not dist_dir:
        return
    root = Path(dist_dir).resolve()
    index = root / INDEX
    if not index.is_file():
        # Fail at startup, not on the first page load (§6 fail fast).
        raise RuntimeError(f"FRONTEND_DIST_DIR={dist_dir} has no {INDEX}; run `npm run build`.")
    api_root = API_PREFIX.strip("/")

    @app.get("/{path:path}", include_in_schema=False)
    def single_page_app(path: str) -> FileResponse:
        # An unknown API path stays a JSON 404, never the app's HTML.
        if path == api_root or path.startswith(f"{api_root}/"):
            raise NotFound("Not Found")
        file = _build_file(root, path)
        if file is not None:
            headers = IMMUTABLE if file.is_relative_to(root / "assets") else REVALIDATE
            return FileResponse(file, headers=headers)
        return FileResponse(index, headers=REVALIDATE)


def _build_file(root: Path, path: str) -> Path | None:
    """The built file ``path`` names inside ``root``, else None (a client route).
    A path no file system accepts (a NUL byte, a name too long) names none."""
    if not path:
        return None
    try:
        file = (root / path).resolve()
        return file if file.is_file() and file.is_relative_to(root) else None
    except (OSError, ValueError):
        return None

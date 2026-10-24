"""The Files API: each user's private workspace, shared with their agents.
Uploads, downloads and deletes go through the real app, onto a real directory.
(That every route needs a signed-in user is checked in test_endpoints.py.)"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import app_settings
from api.models import User
from api.repositories import users
from api.security import hash_password
from api.services import agent_tools
from config.settings import Settings
from tests.conftest import TEST_SETTINGS, bearer

UPLOAD_CAP = 1_000
QUOTA = 2_000


@pytest.fixture
def settings(app: FastAPI, tmp_path: Path) -> Settings:
    """Small limits and a scratch workspace, for this app only."""
    chosen = TEST_SETTINGS.model_copy(
        update={
            "workspace_dir": tmp_path,
            "document_max_bytes": UPLOAD_CAP,
            "workspace_max_total_bytes": QUOTA,
        }
    )
    app.dependency_overrides[app_settings] = lambda: chosen
    return chosen


@pytest.fixture
def files(auth_client: TestClient, settings: Settings) -> TestClient:
    return auth_client


@pytest.fixture
def user_dir(settings: Settings, user: User) -> Path:
    return settings.workspace_dir / f"user-{user.id}"


def upload(client: TestClient, *named: tuple[str, bytes], replace: bool = False) -> httpx.Response:
    return client.post(
        "/api/files",
        files=[("files", (name, data)) for name, data in named],
        data={"replace": "true"} if replace else None,
    )


def listed(client: TestClient) -> list[str]:
    response = client.get("/api/files")
    assert response.status_code == 200
    return [entry["path"] for entry in response.json()["files"]]


# --- listing -------------------------------------------------------------------


def test_an_empty_workspace_lists_nothing_and_the_limits(files: TestClient, user_dir: Path) -> None:
    response = files.get("/api/files")

    assert response.json() == {
        "files": [],
        "used_bytes": 0,
        "quota_bytes": QUOTA,
        "max_file_bytes": UPLOAD_CAP,
        "allowed_extensions": sorted(TEST_SETTINGS.workspace_upload_extensions),
    }
    assert not user_dir.exists()  # looking creates nothing


def test_the_list_is_newest_first_with_sizes_and_types(files: TestClient, user_dir: Path) -> None:
    upload(files, ("old.csv", b"a,b"), ("new.pdf", b"%PDF-1.4"))
    os.utime(user_dir / "old.csv", (1_700_000_000, 1_700_000_000))
    (user_dir / "reports").mkdir()
    (user_dir / "reports" / "q3.md").write_text("# Q3")
    os.utime(user_dir / "reports" / "q3.md", (1_600_000_000, 1_600_000_000))

    body = files.get("/api/files").json()

    assert [(e["path"], e["size"], e["type"]) for e in body["files"]] == [
        ("new.pdf", 8, "pdf"),
        ("old.csv", 3, "csv"),
        ("reports/q3.md", 4, "md"),
    ]
    assert body["files"][1]["modified_at"] == "2023-11-14T22:13:20Z"
    assert body["used_bytes"] == 15


# --- upload ----------------------------------------------------------------------


def test_an_upload_is_stored_under_a_safe_name(files: TestClient, user_dir: Path) -> None:
    response = upload(files, ("C:\\fakepath\\Q3 report?.MD", b"# Hi"))

    assert response.status_code == 201
    (entry,) = response.json()
    assert (entry["path"], entry["size"], entry["type"]) == ("Q3 report_.md", 4, "md")
    assert (user_dir / "Q3 report_.md").read_bytes() == b"# Hi"
    assert user_dir.stat().st_mode & 0o777 == 0o700


def test_several_files_upload_in_one_request(files: TestClient) -> None:
    response = upload(files, ("a.txt", b"a"), ("b.csv", b"x,y"))

    assert response.status_code == 201
    assert sorted(entry["path"] for entry in response.json()) == ["a.txt", "b.csv"]


def test_an_upload_never_overwrites_unless_asked(files: TestClient, user_dir: Path) -> None:
    upload(files, ("notes.txt", b"one"))

    refused = upload(files, ("notes.txt", b"two"))
    assert refused.status_code == 409
    assert refused.json() == {
        "error": "file_exists",
        "detail": "'notes.txt' already exists; choose a new name.",
    }
    assert (user_dir / "notes.txt").read_bytes() == b"one"

    assert upload(files, ("notes.txt", b"two"), replace=True).status_code == 201
    assert (user_dir / "notes.txt").read_bytes() == b"two"
    assert listed(files) == ["notes.txt"]


@pytest.mark.parametrize("name", ["tool.exe", "image.png", "README"])
def test_an_upload_must_have_an_allowed_extension(files: TestClient, name: str) -> None:
    response = upload(files, (name, b"data"))

    assert response.status_code == 415
    assert response.json()["error"] == "unsupported_file_type"
    assert ".pdf" in response.json()["detail"]
    assert listed(files) == []


def test_an_upload_over_the_size_cap_is_refused(files: TestClient) -> None:
    response = upload(files, ("big.txt", b"x" * (UPLOAD_CAP + 1)))

    assert response.status_code == 413
    assert response.json() == {
        "error": "file_too_large",
        "detail": "'big.txt' is larger than the 0.001 MB limit.",
    }
    assert listed(files) == []


def test_uploads_stop_at_the_storage_quota(files: TestClient) -> None:
    assert upload(files, ("a.txt", b"x" * 900)).status_code == 201
    assert upload(files, ("b.txt", b"x" * 900)).status_code == 201

    response = upload(files, ("c.txt", b"x" * 900))

    assert response.status_code == 413
    assert response.json()["error"] == "storage_quota_exceeded"
    assert sorted(listed(files)) == ["a.txt", "b.txt"]


def test_one_bad_file_refuses_the_whole_upload(files: TestClient) -> None:
    assert upload(files, ("good.txt", b"ok"), ("bad.exe", b"MZ")).status_code == 415
    # Two files that end up with one name, and no file at all.
    assert upload(files, ("a.txt", b"1"), ("A/a.txt", b"2")).status_code == 400
    assert files.post("/api/files", data={"replace": "true"}).status_code == 400
    assert listed(files) == []


# --- download --------------------------------------------------------------------


def test_a_download_is_always_an_attachment(files: TestClient) -> None:
    upload(files, ("report.md", b"# Report"))

    response = files.get("/api/files/report.md")

    assert response.status_code == 200
    assert response.content == b"# Report"
    assert response.headers["content-disposition"] == 'attachment; filename="report.md"'
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_stored_html_is_never_rendered_on_the_app_origin(files: TestClient) -> None:
    upload(files, ("page.html", b"<script>alert(document.cookie)</script>"))

    response = files.get("/api/files/page.html")

    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_a_non_ascii_name_downloads_with_an_encoded_filename(files: TestClient) -> None:
    upload(files, ("Отчёт.txt", "текст".encode()))

    response = files.get("/api/files/%D0%9E%D1%82%D1%87%D1%91%D1%82.txt")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        "attachment; filename*=utf-8''%D0%9E%D1%82%D1%87%D1%91%D1%82.txt"
    )


def test_a_file_in_a_folder_downloads_by_its_path(files: TestClient, user_dir: Path) -> None:
    (user_dir / "reports").mkdir(parents=True)
    (user_dir / "reports" / "q3.pdf").write_bytes(b"%PDF-1.4")

    response = files.get("/api/files/reports/q3.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="q3.pdf"'


@pytest.mark.parametrize(
    "path", ["%2E%2E/%2E%2E/etc/passwd", "%2Fetc%2Fpasswd", ".env", "reports/.hidden"]
)
def test_paths_outside_the_workspace_are_refused(
    files: TestClient, user_dir: Path, path: str
) -> None:
    upload(files, ("notes.txt", b"x"))
    (user_dir / ".env").write_text("SECRET=1")

    response = files.get(f"/api/files/{path}")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert files.delete(f"/api/files/{path}").status_code == 400
    assert (user_dir / ".env").exists()


def test_a_link_in_the_workspace_is_not_followed(
    files: TestClient, user_dir: Path, tmp_path: Path
) -> None:
    upload(files, ("notes.txt", b"x"))
    secret = tmp_path / "server-secret.txt"
    secret.write_text("do not serve")
    (user_dir / "linked.txt").symlink_to(secret)

    response = files.get("/api/files/linked.txt")

    assert response.status_code == 400
    assert "do not serve" not in response.text
    assert listed(files) == ["notes.txt"]


# --- delete, ownership, agents ---------------------------------------------------


def test_a_deleted_file_is_gone(files: TestClient) -> None:
    upload(files, ("notes.txt", b"x"))

    assert files.delete("/api/files/notes.txt").status_code == 204
    assert listed(files) == []
    assert files.get("/api/files/notes.txt").status_code == 404
    assert files.delete("/api/files/notes.txt").status_code == 404


def test_one_user_never_reaches_another_users_files(
    files: TestClient, session: Session, user_dir: Path
) -> None:
    stranger = bearer(users.create(session, "stranger", hash_password("stranger-pass-123", 1)))
    upload(files, ("private.txt", b"mine"))

    assert files.get("/api/files", headers=stranger).json()["files"] == []
    assert files.get("/api/files/private.txt", headers=stranger).status_code == 404
    assert files.delete("/api/files/private.txt", headers=stranger).status_code == 404
    assert (user_dir / "private.txt").read_bytes() == b"mine"


def test_agents_and_the_files_page_share_one_directory(
    app: FastAPI, files: TestClient, user: User, settings: Settings
) -> None:
    # A Word file is tens of kilobytes even when short.
    limits = {"workspace_max_file_bytes": 100_000, "workspace_max_total_bytes": 200_000}
    tools_settings = settings.model_copy(
        update={"agent_builtin_tools": ["read_workspace_file", "save_artifact"], **limits}
    )
    app.dependency_overrides[app_settings] = lambda: tools_settings
    native = agent_tools.native_tools(app.state.database, user, tools_settings)
    tools = {tool.name: tool for tool in native}

    saved = tools["save_artifact"].invoke({"path": "summary.docx", "content": "# Summary"})
    upload(files, ("brief.txt", b"Write about bees."))

    assert saved == "Saved summary.docx"
    entries = {entry["path"]: entry["type"] for entry in files.get("/api/files").json()["files"]}
    assert entries == {"summary.docx": "docx", "brief.txt": "txt"}
    download = files.get("/api/files/summary.docx")
    assert download.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert tools["read_workspace_file"].invoke({"path": "brief.txt"}) == "Write about bees."

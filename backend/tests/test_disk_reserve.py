"""The free disk space every write that grows stored data must leave
(WORKSPACE_MIN_FREE_BYTES): runs and pipelines grow the database, which shares
its volume with every account's files. (Files: test_file_storage.py.)"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import app_settings
from api.exceptions import ServerStorageFull
from api.models import Pipeline, Run, RunStatus, User
from api.repositories import runs
from api.services.files.disk import DiskReserve
from tests.conftest import TEST_SETTINGS, FakeProvider
from tests.test_endpoints import make_pipeline

RESERVE = 1_000_000
#: A disk far larger than the reserve, with just less free than it.
FULL = SimpleNamespace(total=10**12, used=0, free=RESERVE - 1)


@pytest.fixture
def nearly_full(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reserve in force, on a disk that has just less free than it."""
    chosen = TEST_SETTINGS.model_copy(update={"workspace_min_free_bytes": RESERVE})
    app.dependency_overrides[app_settings] = lambda: chosen
    monkeypatch.setattr("api.services.files.disk.shutil.disk_usage", lambda _path: FULL)


def test_no_reserve_never_looks_at_the_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    def looked(_path: Path) -> None:
        raise AssertionError("the disk was measured")

    monkeypatch.setattr("api.services.files.disk.shutil.disk_usage", looked)

    DiskReserve(Path("/nowhere"), 0).ensure_room(10)


def test_a_directory_not_made_yet_is_measured_on_its_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    measured: list[Path] = []

    def usage(path: Path) -> SimpleNamespace:
        measured.append(path)
        return FULL

    monkeypatch.setattr("api.services.files.disk.shutil.disk_usage", usage)

    with pytest.raises(ServerStorageFull):
        DiskReserve(tmp_path / "user-9" / "not-yet", RESERVE).ensure_room()
    assert measured == [tmp_path]


@pytest.mark.parametrize(("free", "refused"), [(300_000_000, False), (50_000_000, True)])
def test_on_a_small_disk_the_reserve_is_a_tenth_of_it(
    free: int, refused: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """500 MB asked of a 1 GB volume would refuse half of it: a tenth (100 MB) applies."""
    disk = SimpleNamespace(total=1_000_000_000, used=0, free=free)
    monkeypatch.setattr("api.services.files.disk.shutil.disk_usage", lambda _path: disk)
    reserve = DiskReserve(Path("/"), 500_000_000)

    if refused:
        with pytest.raises(ServerStorageFull):
            reserve.ensure_room()
    else:
        reserve.ensure_room()


@pytest.mark.usefixtures("nearly_full")
def test_no_run_starts_past_the_reserve(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Grows the database")

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "x"})

    assert response.status_code == 507
    assert response.json()["error"] == "storage_full"
    assert session.query(Run).count() == 0


def test_no_run_resumes_past_the_reserve(
    app: FastAPI,
    auth_client: TestClient,
    user: User,
    session: Session,
    fake_provider: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = auth_client.post(
        f"/api/pipelines/{make_pipeline(session, user, 'Stopped').id}/runs", json={"input": "x"}
    ).json()
    runs.set_status(session, started["id"], list(RunStatus), {"status": RunStatus.FAILED})
    chosen = TEST_SETTINGS.model_copy(update={"workspace_min_free_bytes": RESERVE})
    app.dependency_overrides[app_settings] = lambda: chosen
    monkeypatch.setattr("api.services.files.disk.shutil.disk_usage", lambda _path: FULL)

    response = auth_client.post(f"/api/runs/{started['id']}/resume")

    assert response.status_code == 507
    session.expire_all()
    run = session.get(Run, started["id"])
    assert run is not None and run.status == RunStatus.FAILED


@pytest.mark.usefixtures("nearly_full")
def test_no_pipeline_is_saved_past_the_reserve(
    auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    kept = make_pipeline(session, user, "Kept")
    step = {"order": 1, "stage": 1, "prompt": "p {input}", "model": default_model}
    body = {"name": "New", "steps": [step]}

    created = auth_client.post("/api/pipelines/", json=body)
    replaced = auth_client.put(f"/api/pipelines/{kept.id}/", json=body)
    used = auth_client.post("/api/templates/product-launch-plan/use")

    assert [created.status_code, replaced.status_code, used.status_code] == [507, 507, 507]
    assert [pipeline.name for pipeline in session.query(Pipeline)] == ["Kept"]
    # Reading and deleting still work, so space can be freed.
    assert auth_client.get("/api/pipelines/").status_code == 200
    assert auth_client.delete(f"/api/pipelines/{kept.id}/").status_code == 204

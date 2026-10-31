"""The account routes: change the password, take a copy of everything the account
holds, delete it with all its data (GDPR art. 15, 17 and 20). (That each route
needs a signed-in user is checked in test_endpoints.py.)"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import throttling
from api.deps import app_settings
from api.models import (
    ApprovalStatus,
    Integration,
    Pipeline,
    PipelineStep,
    ProviderSetting,
    Run,
    RunApproval,
    RunStep,
    Schedule,
    ScheduleFrequency,
    User,
)
from api.repositories import stored_size, users
from api.security import hash_password
from config.settings import Settings
from tests.conftest import TEST_SETTINGS, FakeProvider, bearer
from tests.test_endpoints import make_pipeline
from tests.test_runs_api import make_active, start

SEALED_KEY = "sealed-api-key-never-exported"
SEALED_HEADERS = "sealed-header-values-never-exported"
NEW_PASSWORD = "a-brand-new-pass-4471"


@pytest.fixture
def settings(app: FastAPI, tmp_path: Path) -> Settings:
    """A scratch workspace, for this app only."""
    chosen = TEST_SETTINGS.model_copy(update={"workspace_dir": tmp_path})
    app.dependency_overrides[app_settings] = lambda: chosen
    return chosen


@pytest.fixture
def account(auth_client: TestClient, settings: Settings) -> TestClient:
    return auth_client


def user_dir(settings: Settings, user: User) -> Path:
    return settings.workspace_dir / f"user-{user.id}"


def fill(session: Session, user: User, client: TestClient, settings: Settings) -> Run:
    """One of everything an account can hold; returns its run."""
    pipeline = make_pipeline(session, user, "Owned", steps=1)
    run = session.get(Run, start(client, pipeline)["id"])
    assert run is not None
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            ProviderSetting(
                user_id=user.id,
                provider="openrouter",
                api_key_encrypted=SEALED_KEY,
                api_key_hint="9xyz",
            ),
            Integration(
                user_id=user.id,
                name="crm",
                url="https://mcp.crm.example/mcp",
                headers_encrypted=SEALED_HEADERS,
                header_hints=[{"name": "Authorization", "hint": "…abcd"}],
            ),
            Schedule(
                user_id=user.id,
                pipeline_id=pipeline.id,
                frequency=ScheduleFrequency.DAILY,
                timezone="Europe/Paris",
                input_text="every morning",
            ),
            RunApproval(
                run_id=run.id,
                step_order=1,
                tool_name="crm_send",
                tool_source="crm",
                arguments={"to": "someone"},
                status=ApprovalStatus.DECLINED,
                expires_at=now + timedelta(minutes=5),
                decided_at=now,
            ),
        ]
    )
    session.commit()
    user_dir(settings, user).mkdir(parents=True)
    (user_dir(settings, user) / "notes.txt").write_text("mine")
    return run


def owned_rows(session: Session, user_id: int) -> dict[str, int]:
    """How many rows of each kind still belong to ``user_id``."""
    run_ids = select(Run.id).where(Run.user_id == user_id).scalar_subquery()
    pipeline_ids = select(Pipeline.id).where(Pipeline.user_id == user_id).scalar_subquery()
    counted = {
        "users": select(func.count()).select_from(User).where(User.id == user_id),
        "pipelines": select(func.count()).select_from(Pipeline).where(Pipeline.user_id == user_id),
        "steps": select(func.count())
        .select_from(PipelineStep)
        .where(PipelineStep.pipeline_id.in_(pipeline_ids)),
        "runs": select(func.count()).select_from(Run).where(Run.user_id == user_id),
        "run_steps": select(func.count()).select_from(RunStep).where(RunStep.run_id.in_(run_ids)),
        "approvals": select(func.count())
        .select_from(RunApproval)
        .where(RunApproval.run_id.in_(run_ids)),
        "schedules": select(func.count()).select_from(Schedule).where(Schedule.user_id == user_id),
        "integrations": select(func.count())
        .select_from(Integration)
        .where(Integration.user_id == user_id),
        "keys": select(func.count())
        .select_from(ProviderSetting)
        .where(ProviderSetting.user_id == user_id),
    }
    return {kind: session.scalar(query) or 0 for kind, query in counted.items()}


def sign_in(client: TestClient, username: str, password: str) -> int:
    payload = {"username": username, "password": password}
    return client.post("/api/login", json=payload).status_code


# --- Password ---------------------------------------------------------------


def test_changing_the_password_ends_the_other_sessions_and_keeps_this_one(
    client: TestClient, user: User, password: str
) -> None:
    client.post("/api/login", json={"username": user.username, "password": password})
    other_device = bearer(user)
    body = {"current_password": password, "new_password": NEW_PASSWORD}

    response = client.post("/api/account/password", json=body, headers=other_device)

    assert response.status_code == 200
    fresh = {"Authorization": f"Bearer {response.json()['access']}"}
    assert client.get("/api/protected", headers=fresh).status_code == 200
    assert client.get("/api/protected", headers=other_device).status_code == 401
    assert client.post("/api/token/refresh").status_code == 200  # the new refresh cookie
    assert sign_in(client, user.username, password) == 401
    assert sign_in(client, user.username, NEW_PASSWORD) == 200


def test_a_wrong_current_password_is_a_400_that_keeps_the_session(
    auth_client: TestClient, user: User, password: str
) -> None:
    body = {"current_password": "not-the-password", "new_password": NEW_PASSWORD}

    response = auth_client.post("/api/account/password", json=body)

    assert response.status_code == 400
    assert response.json()["detail"].startswith("current_password:")
    assert auth_client.get("/api/protected").status_code == 200
    assert sign_in(auth_client, user.username, password) == 200


def test_wrong_passwords_count_toward_the_sign_in_lockout(
    auth_client: TestClient, user: User, password: str
) -> None:
    """A stolen session must not guess the password faster here than at sign-in."""
    limit = TEST_SETTINGS.auth_account_failure_limit
    wrong = {"current_password": "not-the-password", "new_password": NEW_PASSWORD}
    for _ in range(limit):
        assert auth_client.post("/api/account/password", json=wrong).status_code == 400

    right = {"current_password": password, "new_password": NEW_PASSWORD}
    locked = auth_client.post("/api/account/password", json=right)
    deletion = auth_client.post("/api/account/delete", json={"password": password})

    assert (locked.status_code, deletion.status_code) == (429, 429)
    assert sign_in(auth_client, user.username, password) == 429


def test_the_new_password_follows_the_password_rules(
    auth_client: TestClient, password: str
) -> None:
    body = {"current_password": password, "new_password": "too-short"}

    response = auth_client.post("/api/account/password", json=body)

    assert response.status_code == 400
    assert response.json()["detail"].startswith("new_password: This password is too short.")


# --- Export -----------------------------------------------------------------


def test_the_export_holds_everything_the_account_owns_and_no_secret(
    account: TestClient,
    user: User,
    session: Session,
    settings: Settings,
    fake_provider: FakeProvider,
) -> None:
    run = fill(session, user, account, settings)
    neighbour = users.create(session, "neighbour", hash_password("neighbour-pass-1234", 1))
    make_pipeline(session, neighbour, "Not mine")

    response = account.get("/api/account/export")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"
    export: dict[str, Any] = response.json()
    assert export["account"]["username"] == user.username
    assert [p["name"] for p in export["pipelines"]] == ["Owned"]
    assert [r["id"] for r in export["runs"]] == [run.id]
    assert export["runs"][0]["steps"][0]["output"]
    assert [(a["run_id"], a["status"]) for a in export["approvals"]] == [(run.id, "declined")]
    assert export["schedules"][0]["input"] == "every morning"
    assert export["integrations"][0]["headers"] == [{"name": "Authorization", "hint": "…abcd"}]
    assert export["provider_settings"] == [
        {"provider": "openrouter", "default_model": "", "api_key_hint": "9xyz"}
    ]
    assert [f["path"] for f in export["files"]] == ["notes.txt"]
    assert SEALED_KEY not in response.text
    assert SEALED_HEADERS not in response.text
    assert "Not mine" not in response.text


def test_an_account_too_large_to_copy_in_memory_is_refused(
    app: FastAPI, account: TestClient, user: User, session: Session, settings: Settings
) -> None:
    session.add(
        Pipeline(
            user_id=user.id,
            name="Long prompts",
            steps=[PipelineStep(order=1, stage=1, prompt="x" * 500, model="m")],
        )
    )
    session.commit()
    small = settings.model_copy(update={"account_export_max_chars": 100})
    app.dependency_overrides[app_settings] = lambda: small

    response = account.get("/api/account/export")

    assert response.status_code == 422
    assert response.json()["error"] == "export_too_large"


def test_the_size_counts_runs_their_steps_and_prompts_of_this_account_only(
    account: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Measured")
    neighbour = users.create(session, "neighbour", hash_password("neighbour-pass-1234", 1))
    make_pipeline(session, neighbour, "Not counted", steps=3)
    before = stored_size.text_characters(session, user)

    run = session.get(Run, start(account, pipeline, "a" * 1_000)["id"])

    assert run is not None
    grown = stored_size.text_characters(session, user) - before
    step = run.steps[0]
    assert grown >= 1_000 + len(step.input_used) + len(step.output) + len(run.final_output)


def test_one_copy_is_built_at_a_time(account: TestClient) -> None:
    """Each copy holds a whole account in memory: a second one waits its turn."""
    assert throttling._EXPORTING.acquire(blocking=False)
    try:
        busy = account.get("/api/account/export")
    finally:
        throttling._EXPORTING.release()

    assert (busy.status_code, busy.json()["error"]) == (503, "exports_busy")
    assert account.get("/api/account/export").status_code == 200


def test_an_empty_account_exports_cleanly(account: TestClient, user: User) -> None:
    response = account.get("/api/account/export")

    assert response.status_code == 200
    export = json.loads(response.text)
    assert export["pipelines"] == export["runs"] == export["files"] == []
    assert export["note"]


# --- Deletion ---------------------------------------------------------------


def test_deleting_the_account_removes_every_row_and_file_it_owns(
    account: TestClient,
    user: User,
    session: Session,
    settings: Settings,
    fake_provider: FakeProvider,
) -> None:
    fill(session, user, account, settings)
    neighbour = users.create(session, "neighbour", hash_password("neighbour-pass-1234", 1))
    kept = make_pipeline(session, neighbour, "Not mine")
    user_id, folder = user.id, user_dir(settings, user)
    assert all(owned_rows(session, user_id).values())

    response = account.post("/api/account/delete", json={"password": "pipeline-test-pass-123"})

    assert response.status_code == 204
    assert 'aimix_refresh=""' in response.headers["set-cookie"]
    session.expire_all()
    assert owned_rows(session, user_id) == dict.fromkeys(owned_rows(session, user_id), 0)
    assert not folder.exists()
    assert session.get(Pipeline, kept.id) is not None
    assert account.get("/api/protected").status_code == 401


def test_a_wrong_password_deletes_nothing(
    account: TestClient, user: User, session: Session, settings: Settings
) -> None:
    user_dir(settings, user).mkdir(parents=True)

    response = account.post("/api/account/delete", json={"password": "not-the-password"})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("password:")
    assert session.get(User, user.id) is not None
    assert user_dir(settings, user).exists()


def test_an_account_with_an_active_run_is_not_deleted(
    account: TestClient,
    user: User,
    session: Session,
    password: str,
    fake_provider: FakeProvider,
) -> None:
    run = start(account, make_pipeline(session, user, "Busy"))
    make_active(session, run["id"])

    response = account.post("/api/account/delete", json={"password": password})

    assert response.status_code == 409
    assert session.get(User, user.id) is not None
    assert session.get(Run, run["id"]) is not None


def test_a_new_account_never_finds_the_files_of_a_deleted_one(
    client: TestClient, session: Session, settings: Settings
) -> None:
    """SQLite hands a deleted account's id to the next one: whatever is still
    filed under that id is gone before the new account can read it."""
    first = users.create(session, "first", hash_password("first-account-pass-1", 1))
    first_id = first.id
    users.delete(session, first)
    leftover = settings.workspace_dir / f"user-{first_id}"
    leftover.mkdir(parents=True)
    (leftover / "private.txt").write_text("the first account's")

    created = client.post(
        "/api/register", json={"username": "second", "password": "second-account-pass-2"}
    )

    assert created.status_code == 201
    second = users.get_by_username(session, "second")
    assert second is not None and second.id == first_id
    assert not leftover.exists()


@pytest.mark.usefixtures("settings")
def test_a_deleted_accounts_token_never_signs_in_as_the_next_account(
    client: TestClient, session: Session
) -> None:
    """SQLite gives the deleted account's id to the next one: the old access token,
    still unexpired, must not open the new account."""
    first = {"username": "first", "password": "first-account-pass-1"}
    client.post("/api/register", json=first)
    old = {"Authorization": f"Bearer {client.post('/api/login', json=first).json()['access']}"}
    first_id = users.get_by_username(session, "first").id  # type: ignore[union-attr]
    deleted = client.post("/api/account/delete", json={"password": first["password"]}, headers=old)
    assert deleted.status_code == 204

    second = {"username": "second", "password": "second-account-pass-2"}
    client.post("/api/register", json=second)
    session.expire_all()
    newcomer = users.get_by_username(session, "second")

    assert newcomer is not None and newcomer.id == first_id
    assert client.get("/api/protected", headers=old).status_code == 401
    assert client.get("/api/account/export", headers=old).status_code == 401
    fresh = client.post("/api/login", json=second).json()["access"]
    assert (
        client.get("/api/protected", headers={"Authorization": f"Bearer {fresh}"}).json()["user_id"]
        == first_id
    )


def test_a_deleted_username_can_be_registered_again(
    account: TestClient, user: User, password: str
) -> None:
    account.post("/api/account/delete", json={"password": password})

    again = account.post(
        "/api/register", json={"username": user.username, "password": "a-strong-pass-9182"}
    )

    assert again.status_code == 201

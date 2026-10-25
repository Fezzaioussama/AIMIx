"""The approval endpoints: the same answer twice changes nothing, a clash or an
expired request is a 409, and everything is scoped to the run's owner."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import ApprovalStatus, RunApproval, User
from api.repositories import users
from api.security import hash_password
from tests.approval_fakes import ARGUMENTS, approval_status, request_approval, running_run
from tests.conftest import bearer
from tests.test_endpoints import make_pipeline


def waiting_run(app: FastAPI, session: Session, owner: User, **request: Any) -> tuple[int, int]:
    """A running run of ``owner``'s with one request waiting; their ids."""
    run_id = running_run(app.state.database, owner, make_pipeline(session, owner, "Flow"))
    return run_id, request_approval(session, run_id, **request).id


def path(run_id: int, approval_id: int, answer: str) -> str:
    return f"/api/runs/{run_id}/approvals/{approval_id}/{answer}"


def test_a_waiting_run_shows_its_owner_what_it_asks(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, approval_id = waiting_run(app, session, user)

    run = auth_client.get(f"/api/runs/{run_id}").json()

    assert run["status"] == "waiting"
    [asked] = run["pending_approvals"]
    assert asked["id"] == approval_id
    assert set(asked) == {
        "id",
        "step_order",
        "tool_name",
        "tool_source",
        "tool_description",
        "arguments",
        "arguments_truncated",
        "status",
        "created_at",
        "expires_at",
    }
    assert (asked["tool_name"], asked["tool_source"], asked["step_order"]) == (
        "crm_send_email",
        "crm",
        1,
    )
    assert (asked["arguments"], asked["arguments_truncated"]) == (ARGUMENTS, False)
    assert asked["status"] == "pending"
    assert asked["expires_at"].endswith(("Z", "+00:00"))


def test_a_run_nothing_waits_on_lists_no_requests(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id = running_run(app.state.database, user, make_pipeline(session, user, "Flow"))

    run = auth_client.get(f"/api/runs/{run_id}").json()

    assert (run["status"], run["pending_approvals"]) == ("running", [])


def test_approving_lets_the_run_go_on(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, approval_id = waiting_run(app, session, user)

    response = auth_client.post(path(run_id, approval_id, "approve"))

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["pending_approvals"]) == ("running", [])
    assert approval_status(app.state.database, approval_id) == ApprovalStatus.APPROVED


def test_declining_refuses_the_call_and_the_run_goes_on(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, approval_id = waiting_run(app, session, user)

    response = auth_client.post(path(run_id, approval_id, "decline"))

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert approval_status(app.state.database, approval_id) == ApprovalStatus.DECLINED


def test_the_same_answer_twice_changes_nothing(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, approval_id = waiting_run(app, session, user)
    first = auth_client.post(path(run_id, approval_id, "approve"))
    session.expire_all()
    decided_at = session.get(RunApproval, approval_id).decided_at  # type: ignore[union-attr]

    second = auth_client.post(path(run_id, approval_id, "approve"))

    assert first.status_code == second.status_code == 200
    session.expire_all()
    assert session.get(RunApproval, approval_id).decided_at == decided_at  # type: ignore[union-attr]


def test_the_other_answer_after_a_decision_is_a_conflict(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    approved_run, approved = waiting_run(app, session, user)
    declined_run, declined = waiting_run(app, session, user)
    auth_client.post(path(approved_run, approved, "approve"))
    auth_client.post(path(declined_run, declined, "decline"))

    late_decline = auth_client.post(path(approved_run, approved, "decline"))
    late_approve = auth_client.post(path(declined_run, declined, "approve"))

    assert late_decline.status_code == late_approve.status_code == 409
    assert late_decline.json() == {
        "error": "conflict",
        "detail": "This action was already approved.",
    }
    assert late_approve.json()["detail"] == "This action was already declined."
    assert approval_status(app.state.database, approved) == ApprovalStatus.APPROVED
    assert approval_status(app.state.database, declined) == ApprovalStatus.DECLINED


def test_a_request_past_its_time_can_no_longer_be_answered(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, approval_id = waiting_run(app, session, user, expires_in=timedelta(seconds=-1))

    approve = auth_client.post(path(run_id, approval_id, "approve"))
    decline = auth_client.post(path(run_id, approval_id, "decline"))

    assert approve.status_code == decline.status_code == 409
    assert "expired" in approve.json()["detail"]
    assert approval_status(app.state.database, approval_id) == ApprovalStatus.EXPIRED


@pytest.fixture
def waiting(app: FastAPI, session: Session, user: User) -> tuple[int, int]:
    """The ids of a running run of ``user``'s and the one request it waits on."""
    return waiting_run(app, session, user)


def test_stopping_the_run_expires_its_requests(
    app: FastAPI,
    auth_client: TestClient,
    waiting: tuple[int, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id, approval_id = waiting

    with caplog.at_level(logging.INFO):
        stopped = auth_client.post(f"/api/runs/{run_id}/cancel").json()
    late = auth_client.post(path(run_id, approval_id, "approve"))

    assert (stopped["status"], stopped["pending_approvals"]) == ("cancelled", [])
    assert approval_status(app.state.database, approval_id) == ApprovalStatus.EXPIRED
    assert late.status_code == 409
    assert "expired" in late.json()["detail"]
    # The request that was asked about is accounted for in the log, without its arguments.
    assert f"approval.decided run_id={run_id} approval_id={approval_id}" in caplog.text
    assert "outcome=expired" in caplog.text
    assert "ada@example.com" not in caplog.text


def test_a_run_stays_waiting_until_every_request_is_answered(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, first = waiting_run(app, session, user)
    second = request_approval(session, run_id, step=2).id

    after_first = auth_client.post(path(run_id, first, "approve")).json()
    after_second = auth_client.post(path(run_id, second, "decline")).json()

    assert after_first["status"] == "waiting"
    assert [asked["id"] for asked in after_first["pending_approvals"]] == [second]
    assert after_second["status"] == "running"


def test_a_waiting_run_is_in_progress_so_it_is_stopped_before_it_is_deleted(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, _ = waiting_run(app, session, user)

    refused = auth_client.delete(f"/api/runs/{run_id}")
    auth_client.post(f"/api/runs/{run_id}/cancel")
    deleted = auth_client.delete(f"/api/runs/{run_id}")

    assert refused.status_code == 409
    assert deleted.status_code == 204


def test_the_history_can_be_filtered_by_status(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    waiting, _ = waiting_run(app, session, user)
    running_run(app.state.database, user, make_pipeline(session, user, "Quiet"))

    only_waiting = auth_client.get("/api/runs", params={"status": "waiting", "limit": 1}).json()
    unknown = auth_client.get("/api/runs", params={"status": "paused"})

    assert only_waiting["total"] == 1
    assert [item["id"] for item in only_waiting["items"]] == [waiting]
    assert only_waiting["items"][0]["status"] == "waiting"
    assert unknown.status_code == 400
    assert unknown.json()["error"] == "validation_error"


def test_only_the_runs_owner_can_answer(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id, approval_id = waiting_run(app, session, user)
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    theirs, _ = waiting_run(app, session, stranger)

    for answer in ("approve", "decline"):
        refused = auth_client.post(path(run_id, approval_id, answer), headers=bearer(stranger))
        assert refused.status_code == 404, answer
        assert refused.json()["error"] == "not_found"
        # Another run's request id under one of your own runs is not found either.
        assert auth_client.post(path(theirs, approval_id, answer)).status_code == 404
        assert auth_client.post(path(run_id, approval_id + 99, answer)).status_code == 404
    assert approval_status(app.state.database, approval_id) == ApprovalStatus.PENDING

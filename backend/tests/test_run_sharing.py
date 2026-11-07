"""A run's report shared by secret link: made by its owner once the run has ended,
read by anyone who has the link without what the run was given, and withdrawn."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import RunShare, User
from api.repositories import users
from api.security import hash_password
from api.services.run_sharing import NOT_SHARED
from tests.conftest import FakeProvider, bearer
from tests.test_endpoints import make_pipeline
from tests.test_runs_api import make_active, start


def share(client: TestClient, run_id: int, method: str = "POST") -> Any:
    return client.request(method, f"/api/runs/{run_id}/share")


def test_the_owner_shares_an_ended_run_and_anyone_with_the_link_reads_its_report(
    auth_client: TestClient,
    client: TestClient,
    user: User,
    session: Session,
    fake_provider: FakeProvider,
) -> None:
    pipeline = make_pipeline(session, user, "Digest", steps=2)
    run = start(auth_client, pipeline, "the secret brief")
    assert share(auth_client, run["id"], "GET").json() is None

    made = share(auth_client, run["id"])
    again = share(auth_client, run["id"])
    shown = share(auth_client, run["id"], "GET")
    public = client.get(f"/api/shared/{made.json()['token']}")

    assert made.status_code == 200, made.text
    assert made.json()["url"].endswith(f"/shared/{made.json()['token']}")
    assert again.json()["token"] == made.json()["token"]  # made once
    assert shown.json() == made.json()
    assert public.status_code == 200, public.text
    report = public.json()
    assert report["pipeline_name"] == "Digest"
    assert report["final_output"] == "fake reply"
    assert [step["output"] for step in report["steps"]] == ["fake reply", "fake reply"]
    # What the run was given, its prompts and the owner's own things stay private.
    assert (report["input"], report["inputs"], report["pending_approvals"]) == ("", {}, [])
    assert all(step["input_used"] == "" for step in report["steps"])
    assert all(step["prompt"] == "" for step in report["definition"]["steps"])
    assert (report["rating"], report["feedback"]) == (None, "")
    assert [step["title"] for step in report["definition"]["steps"]] == [
        step["title"] for step in run["definition"]["steps"]
    ]


def test_a_withdrawn_or_unknown_link_shows_nothing(
    auth_client: TestClient,
    client: TestClient,
    user: User,
    session: Session,
    fake_provider: FakeProvider,
) -> None:
    run_id = start(auth_client, make_pipeline(session, user, "Digest"))["id"]
    token = share(auth_client, run_id).json()["token"]

    withdrawn = share(auth_client, run_id, "DELETE")
    gone = client.get(f"/api/shared/{token}")
    unknown = client.get("/api/shared/not-a-token")

    assert withdrawn.status_code == 204
    assert share(auth_client, run_id, "DELETE").status_code == 204  # nothing to withdraw is fine
    assert share(auth_client, run_id, "GET").json() is None
    assert (gone.status_code, gone.json()["detail"]) == (404, NOT_SHARED)
    assert unknown.status_code == 404
    # A new share is a new link; the old one stays dead.
    renewed = share(auth_client, run_id).json()["token"]
    assert renewed != token
    assert client.get(f"/api/shared/{renewed}").status_code == 200


def test_only_an_ended_run_of_the_owners_can_be_shared(
    auth_client: TestClient,
    client: TestClient,
    session: Session,
    user: User,
    fake_provider: FakeProvider,
) -> None:
    run_id = start(auth_client, make_pipeline(session, user, "Digest"))["id"]
    make_active(session, run_id)
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    theirs = make_pipeline(session, stranger, "Theirs")
    their_run = client.post(
        f"/api/pipelines/{theirs.id}/runs", json={"input": "go"}, headers=bearer(stranger)
    ).json()

    too_early = share(auth_client, run_id)

    assert (too_early.status_code, too_early.json()["error"]) == (409, "conflict")
    assert too_early.json()["detail"] == "Share the run once it has ended."
    for method in ("GET", "POST", "DELETE"):
        assert share(auth_client, their_run["id"], method).status_code == 404, method


def test_the_link_is_kept_hashed_and_sealed_and_dies_with_the_run(
    auth_client: TestClient,
    client: TestClient,
    user: User,
    session: Session,
    fake_provider: FakeProvider,
) -> None:
    run_id = start(auth_client, make_pipeline(session, user, "Digest"))["id"]
    token = share(auth_client, run_id).json()["token"]

    stored = session.scalar(select(RunShare).where(RunShare.run_id == run_id))
    assert stored is not None
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored.token_encrypted
    assert auth_client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get(f"/api/shared/{token}").status_code == 404
    session.expire_all()
    assert session.scalar(select(RunShare).where(RunShare.run_id == run_id)) is None

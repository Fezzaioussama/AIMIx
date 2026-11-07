"""A workflow's results emailed: an email address set by chat, confirmed with a first
email, then each run's result sent with the files the run saved attached."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import User
from api.services.deliveries import service
from api.services.deliveries.attachments import RunWindow, saved_during
from api.services.deliveries.formats import EMAIL_HELLO, RunMessage, body_for, kind_of
from api.services.deliveries.sender import ResultDeliveries, SendPolicy
from api.services.deliveries.service import DeliveryAccess, checked_address, destination_of
from api.services.email import Attachment, Email, NullSender, SmtpSender, SmtpSettings
from api.services.files.storage import WorkspaceStorage
from api.services.run_policy import RunPolicy
from api.services.run_recorder import utcnow
from api.services.runs import RunService, RunStart
from api.webhook_deps import delivery_sending
from tests.conftest import FakeProvider, InlineRunExecutor, bearer
from tests.email_fakes import Outbox, Refusing
from tests.test_deliveries import BOX, workflow
from tests.test_email import connecting

ADA = "ada@example.com"
MAILTO_ADA = f"mailto:{ADA}"


def email_policy(sender: Any, max_bytes: int = 1_000_000) -> SendPolicy:
    return SendPolicy(5, 20_000, email=sender, attachment_max_bytes=max_bytes)


def workspace(tmp_path: Path) -> WorkspaceStorage:
    storage = WorkspaceStorage(tmp_path / "workspace", 10_000_000, 100)
    storage.prepare()
    return storage


def aged(storage: WorkspaceStorage, name: str, data: bytes, seconds_ago: float) -> None:
    """A file saved ``seconds_ago``."""
    path = storage.save(name, data)
    moment = utcnow().timestamp() - seconds_ago
    os.utime(path, (moment, moment))


# --- the address and the message ---------------------------------------------------------


def test_an_email_address_is_accepted_plain_or_as_mailto_and_shown_by_its_domain() -> None:
    assert checked_address(f"  {ADA} ") == MAILTO_ADA
    assert checked_address(MAILTO_ADA) == MAILTO_ADA
    assert kind_of(MAILTO_ADA) == "email"
    assert destination_of(MAILTO_ADA) == "example.com"
    assert destination_of("https://Hooks.Slack.com/x") == "hooks.slack.com"
    with pytest.raises(ValidationFailed, match="Give an email address, or a full address"):
        checked_address("mailto:not-an-address")
    with pytest.raises(ValidationFailed, match="at most"):
        checked_address(f"{'a' * 300}@example.com")


def test_the_email_carries_the_headline_and_the_result() -> None:
    ended = RunMessage("Digest", "succeeded", "x" * 30, run_id=7)

    assert body_for("email", ended, 10) == {"subject": "Digest finished", "text": "x" * 10}
    assert body_for("email", RunMessage("Digest", "ready", ""), 10) == {
        "subject": "Digest will send its results here",
        "text": EMAIL_HELLO,
    }


def test_an_attachment_travels_as_a_mime_part() -> None:
    opened: list[Any] = []
    settings = SmtpSettings("smtp.example", 587, "", "", "AIMIx <no-reply@x.io>", "none", 5)
    attachment = Attachment("report.md", b"# Report", "text/markdown")

    SmtpSender(settings, connect=connecting(opened)).send(Email(ADA, "Hi", "Body", (attachment,)))

    (part,) = list(opened[0].messages[0].iter_attachments())
    assert (part.get_filename(), part.get_content_type()) == ("report.md", "text/markdown")
    assert part.get_content() == "# Report"


# --- confirmed by a click, then each run ---------------------------------------------------


def test_confirming_sends_a_first_email_then_each_run_emails_its_result_with_its_files(
    app: FastAPI, client: TestClient, session: Session, user: User, tmp_path: Path
) -> None:
    outbox = Outbox()
    app.dependency_overrides[delivery_sending] = lambda: email_policy(outbox)
    access = DeliveryAccess(session, user, BOX)
    pipeline = workflow(session, user)
    view = service.set_address(access, pipeline.id, ADA)
    assert (view.service, view.destination, view.confirmed) == ("Email", "example.com", False)

    confirmed = client.post(f"/api/deliveries/{view.id}/confirm", headers=bearer(user))

    assert confirmed.status_code == 200 and confirmed.json()["confirmed"] is True
    assert outbox.sent == [Email(ADA, "Digest will send its results here", EMAIL_HELLO)]

    storage = workspace(tmp_path)
    aged(storage, "old-notes.md", b"before the run", seconds_ago=3600)
    storage.save("report.md", b"# Report")
    sender = ResultDeliveries(BOX, email_policy(outbox), lambda user_id: storage)
    runs = RunService(app.state.database, InlineRunExecutor(), 1, RunPolicy(deliveries=sender))
    runs.start(user, pipeline, RunStart("bees"), FakeProvider("Buzz"))

    sent = outbox.sent[1]
    assert (sent.to, sent.subject, sent.text) == (ADA, "Digest finished", "Buzz")
    assert sent.attachments == (Attachment("report.md", b"# Report", "text/markdown"),)


def test_the_files_fit_the_cap_newest_first(tmp_path: Path) -> None:
    storage = workspace(tmp_path)
    aged(storage, "big.bin", b"x" * 60, seconds_ago=3)
    aged(storage, "mid.txt", b"m" * 30, seconds_ago=2)
    aged(storage, "small.txt", b"s" * 20, seconds_ago=1)
    window = RunWindow((utcnow() - timedelta(seconds=10)).replace(tzinfo=None), None)

    chosen = saved_during(storage, window, max_bytes=50)

    assert [item.filename for item in chosen] == ["small.txt", "mid.txt"]
    assert saved_during(storage, window, max_bytes=0) == ()


def test_without_a_mail_server_an_email_address_cannot_be_confirmed(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    app.dependency_overrides[delivery_sending] = lambda: email_policy(NullSender())
    view = service.set_address(DeliveryAccess(session, user, BOX), workflow(session, user).id, ADA)

    refused = client.post(f"/api/deliveries/{view.id}/confirm", headers=bearer(user))

    assert (refused.status_code, refused.json()["error"]) == (502, "delivery_failed")
    assert "cannot send email" in refused.json()["detail"]
    app.dependency_overrides[delivery_sending] = lambda: email_policy(Refusing())
    again = client.post(f"/api/deliveries/{view.id}/confirm", headers=bearer(user))
    assert again.status_code == 502 and "did not take the message" in again.json()["detail"]
    assert (
        client.get(f"/api/deliveries/{view.id}", headers=bearer(user)).json()["confirmed"] is False
    )

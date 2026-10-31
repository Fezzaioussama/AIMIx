"""The operator commands that answer a data-protection request made outside the
app: export-user prints everything an account holds, delete-user deletes it."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from api import cli
from api.db import Database
from api.models import Base, Pipeline, User
from api.repositories import users
from api.security import hash_password
from config.settings import Settings, pin_settings
from tests.conftest import TEST_SETTINGS


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[Settings]:
    """A database file and a workspace the commands open themselves."""
    chosen = TEST_SETTINGS.model_copy(
        update={
            "database_url": f"sqlite:///{tmp_path / 'cli.sqlite3'}",
            "workspace_dir": tmp_path / "workspace",
        }
    )
    Base.metadata.create_all(Database(chosen.database_url).engine)
    pin_settings(chosen)
    yield chosen
    pin_settings(TEST_SETTINGS)


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    with Database(settings.database_url).session() as db:
        yield db


@pytest.fixture
def alice(session: Session, settings: Settings) -> User:
    user = users.create(session, "alice", hash_password("alice-account-pass", 1))
    session.add(Pipeline(user_id=user.id, name="Alice's", steps=[]))
    session.commit()
    folder = settings.workspace_dir / f"user-{user.id}"
    folder.mkdir(parents=True)
    (folder / "report.md").write_text("# mine")
    return user


def test_export_user_prints_the_account_as_json(
    alice: User, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["export-user", "alice"]) == 0

    export = json.loads(capsys.readouterr().out)
    assert export["account"]["username"] == "alice"
    assert [p["name"] for p in export["pipelines"]] == ["Alice's"]
    assert [f["path"] for f in export["files"]] == ["report.md"]


def test_delete_user_asks_for_the_name_then_deletes_everything(
    alice: User, settings: Settings, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice")
    folder = settings.workspace_dir / f"user-{alice.id}"

    assert cli.main(["delete-user", "alice"]) == 0

    session.expire_all()
    assert users.get_by_username(session, "alice") is None
    assert session.query(Pipeline).count() == 0
    assert not folder.exists()


def test_delete_user_deletes_nothing_without_the_name_typed(
    alice: User, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

    assert cli.main(["delete-user", "alice"]) == 1
    assert users.get_by_username(session, "alice") is not None


def test_an_unknown_username_is_reported(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["export-user", "nobody"]) == 1
    assert "There is no account named nobody." in capsys.readouterr().err

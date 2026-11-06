"""save_artifact in a run: an agent replaces its own draft but never a file from before
the run, and hears how many pages a PDF came out on, so a one-page brief that ran onto
two pages can be shortened and saved again under the same name."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from langchain_core.tools import ToolException

from api.db import Database
from api.models import Base, Run, User
from api.services import agent_tools
from api.services.agent_types import RunStepRef
from api.services.files.storage import WorkspaceStorage
from api.services.multiagent.step_agent import run_tools
from api.services.toolbox.config import WorkspaceOptions
from api.services.toolbox.questions import RunTools
from api.services.toolbox.workspace import LocalWorkspace
from tests.approval_fakes import make_owner, make_pipeline, running_run
from tests.test_toolbox import RENDER, WORKSPACE_LIMITS

LIMITS = replace(WORKSPACE_LIMITS, max_file_bytes=500_000)
PLAN = "# Launch plan\n\nOne sourdough loaf every Saturday."


def workspace(root: Path, drafts_since: datetime | None) -> LocalWorkspace:
    storage = WorkspaceStorage(root, 5_000_000, max_files=1_000)
    return LocalWorkspace(storage, LIMITS, RENDER, WorkspaceOptions(drafts_since=drafts_since))


def an_hour_ago() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=1)


@pytest.fixture
def database() -> Iterator[Database]:
    db = Database("sqlite://")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


def test_saving_again_replaces_the_draft_this_run_saved(tmp_path: Path) -> None:
    run = workspace(tmp_path, an_hour_ago())

    assert run.save_artifact("plan.pdf", PLAN) == "Saved plan.pdf (1 page)"
    first = (tmp_path / "plan.pdf").read_bytes()
    assert run.save_artifact("plan.pdf", PLAN + " Shorter.") == "Replaced plan.pdf (1 page)"
    assert (tmp_path / "plan.pdf").read_bytes() != first
    assert [path.name for path in tmp_path.iterdir()] == ["plan.pdf"]


def test_a_file_from_before_the_run_is_never_replaced(tmp_path: Path) -> None:
    (tmp_path / "plan.md").write_text("The user's own plan")
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    os.utime(tmp_path / "plan.md", (two_days_ago, two_days_ago))

    with pytest.raises(ToolException, match="already exists"):
        workspace(tmp_path, an_hour_ago()).save_artifact("plan.md", "An agent's plan")
    assert (tmp_path / "plan.md").read_text() == "The user's own plan"


def test_outside_a_run_nothing_is_replaced(tmp_path: Path) -> None:
    chat = workspace(tmp_path, None)
    chat.save_artifact("notes.md", "first")

    with pytest.raises(ToolException, match="already exists"):
        chat.save_artifact("notes.md", "second")
    assert (tmp_path / "notes.md").read_text() == "first"


def test_a_pdf_longer_than_a_page_says_how_many_pages_it_has(tmp_path: Path) -> None:
    long_plan = "\n\n".join(f"Paragraph {n}: " + "every Saturday " * 30 for n in range(40))

    reply = workspace(tmp_path, None).save_artifact("long.pdf", long_plan)

    assert reply.startswith("Saved long.pdf (") and reply.endswith(" pages)")
    assert int(reply.removeprefix("Saved long.pdf (").removesuffix(" pages)")) >= 2


def test_a_runs_agents_get_the_drafts_rule_through_their_tools(
    app: FastAPI, user: User, tmp_path: Path
) -> None:
    settings = agent_tools.get_settings().model_copy(
        update={"workspace_dir": tmp_path, "agent_builtin_tools": ["save_artifact"]}
    )

    def save_twice(drafts_since: datetime | None, path: str) -> str:
        tools = agent_tools.native_tools(app.state.database, user, settings, RunTools(drafts_since))
        save = next(tool for tool in tools if tool.name == "save_artifact")
        save.invoke({"path": path, "content": "first"})
        return str(save.invoke({"path": path, "content": "second"}))

    assert save_twice(an_hour_ago(), "run.md") == "Replaced run.md"
    assert "already exists" in save_twice(None, "chat.md")


def test_the_drafts_rule_starts_when_the_run_did(database: Database) -> None:
    owner = make_owner(database)
    run_id = running_run(database, owner, make_pipeline(database, owner))
    started = datetime(2026, 11, 1, 18, 0)  # as SQLite hands it back: UTC, no zone
    with database.session() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.started_at = started
        session.commit()

    watched = run_tools(database, RunStepRef(run_id, 1), None)
    assert watched.drafts_since == started.replace(tzinfo=timezone.utc)
    assert run_tools(database, None, None).drafts_since is None

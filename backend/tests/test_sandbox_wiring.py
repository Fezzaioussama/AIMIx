"""run_python's wiring: offered only with an E2B key, subject to the data-leak
rule, configured from settings, and bound to the signed-in user's workspace.
No network and no E2B key is ever used."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from api.models import User
from api.repositories import users
from api.security import hash_password
from api.services import agent_tools
from api.services.toolbox import registry
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.registry import toolbox_tools
from api.services.toolbox.sandbox import CodeExecution
from config.settings import Settings
from tests.conftest import TEST_SETTINGS, UNUSED_WORKSPACE
from tests.sandbox_fakes import FakeSandbox, Opener, call

CONFIG = replace(toolbox_config(TEST_SETTINGS, UNUSED_WORKSPACE), sandbox_api_key="")


def test_run_python_is_offered_only_with_an_e2b_key(tmp_path: Path) -> None:
    config = replace(CONFIG, enabled=("calculator", "run_python"), workspace_dir=tmp_path)

    assert [item.name for item in toolbox_tools(config)] == ["calculator"]
    keyed = replace(config, sandbox_api_key="e2b-test")
    assert [item.name for item in toolbox_tools(keyed)] == ["calculator", "run_python"]


def test_run_python_counts_as_a_workspace_reader_but_not_as_outbound(tmp_path: Path) -> None:
    """Its input_files read the workspace, so the web tools go unless the operator
    opts in; its sandbox has no internet, so it stays next to the readers."""
    config = replace(
        CONFIG,
        enabled=("web_search", "fetch_url", "run_python"),
        workspace_dir=tmp_path,
        search_api_key="tvly-test",
        sandbox_api_key="e2b-test",
    )

    assert [item.name for item in toolbox_tools(config)] == ["run_python"]
    opted_in = replace(config, allow_workspace_network_access=True)
    assert [item.name for item in toolbox_tools(opted_in)] == [
        "web_search",
        "fetch_url",
        "run_python",
    ]
    with_readers = replace(config, enabled=("read_workspace_file", "run_python"))
    assert [item.name for item in toolbox_tools(with_readers)] == [
        "read_workspace_file",
        "run_python",
    ]


def test_run_python_without_a_key_does_not_take_the_web_tools_away(tmp_path: Path) -> None:
    """Only readers that are actually offered can leak workspace data."""
    config = replace(
        CONFIG,
        enabled=("web_search", "fetch_url", "run_python"),
        workspace_dir=tmp_path,
        search_api_key="tvly-test",
    )

    assert [item.name for item in toolbox_tools(config)] == ["web_search", "fetch_url"]


@pytest.mark.asyncio
async def test_run_python_uses_the_signed_in_users_own_workspace(
    app: FastAPI, user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = FakeSandbox(CodeExecution(), {"result.txt": b"done"})
    created: list[tuple[Any, ...]] = []

    def opener(*options: Any) -> Opener:
        created.append(options)
        return Opener(sandbox)

    monkeypatch.setattr(registry, "E2BSandboxOpener", opener)
    settings = TEST_SETTINGS.model_copy(
        update={
            "workspace_dir": tmp_path,
            "agent_builtin_tools": ["run_python"],
            "e2b_api_key": "e2b-test",
        }
    )
    own = tmp_path / f"user-{user.id}"
    own.mkdir(mode=0o700)
    (own / "mine.csv").write_text("a\n")
    (tmp_path / "theirs.csv").write_text("other user\n")
    native = agent_tools.native_tools(app.state.database, user, settings)
    tool = next(item for item in native if item.name == "run_python")

    await call(tool, code="go()", input_files=["mine.csv"])
    refused = await call(tool, code="go()", input_files=["../theirs.csv"])

    assert created == [
        ("e2b-test", settings.sandbox_timeout_seconds, settings.sandbox_max_stream_chars)
    ]
    assert sandbox.uploads == {"mine.csv": b"a\n"}
    assert [path.read_bytes() for path in (own / "sandbox").rglob("result.txt")] == [b"done"]
    assert refused.status == "error"


@pytest.mark.parametrize("placeholder", ["your_api_key_here", "change-me", " "])
def test_a_placeholder_e2b_key_counts_as_unset(placeholder: str) -> None:
    assert Settings(_env_file=None, E2B_API_KEY=placeholder).e2b_api_key == ""


def test_sandbox_settings_reach_the_toolbox_without_showing_the_key() -> None:
    settings = Settings(
        _env_file=None,
        E2B_API_KEY="e2b-real-looking-key",
        SANDBOX_TIMEOUT_SECONDS="30",
        SANDBOX_MAX_OUTPUT_CHARS="2000",
        SANDBOX_MAX_FILES="4",
        SANDBOX_MAX_STREAM_CHARS="9000",
    )
    config = toolbox_config(settings, UNUSED_WORKSPACE)

    assert "run_python" in Settings.model_fields["agent_builtin_tools"].default
    assert (config.sandbox_api_key, config.sandbox_timeout_seconds) == ("e2b-real-looking-key", 30)
    assert (config.sandbox_max_output_chars, config.sandbox_max_files) == (2000, 4)
    assert config.sandbox_max_stream_chars == 9000
    assert "e2b-real-looking-key" not in repr(config)


def test_the_toolbox_needs_the_users_own_folder() -> None:
    # No fallback to AGENT_WORKSPACE_DIR itself, which holds every user's folder.
    with pytest.raises(TypeError, match="workspace_dir"):
        toolbox_config(TEST_SETTINGS)  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_each_account_has_an_hourly_allowance_of_run_python_calls(
    app: FastAPI,
    session: Session,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = Opener()
    monkeypatch.setattr(registry, "E2BSandboxOpener", lambda *options: opener)
    settings = TEST_SETTINGS.model_copy(
        update={
            "workspace_dir": tmp_path,
            "agent_builtin_tools": ["run_python"],
            "e2b_api_key": "e2b-test",
            "sandbox_max_calls_per_hour": 2,
        }
    )
    other = users.create(session, "other-user", hash_password("pw-other-123", iterations=1))

    def run_python(owner: User) -> Any:
        native = agent_tools.native_tools(app.state.database, owner, settings)
        return next(item for item in native if item.name == "run_python")

    mine = run_python(user)
    assert [(await call(mine, code="go()")).status for _ in range(2)] == ["success"] * 2
    refused = await call(mine, code="go()")
    theirs = await call(run_python(other), code="go()")

    assert refused.status == "error"
    assert "limited to 2 calls an hour" in str(refused.content)
    assert theirs.status == "success"
    assert len(opener.opened) == 3  # the refused call never created a sandbox

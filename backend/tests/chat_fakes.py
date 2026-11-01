"""Builders for the chat tool tests: a ``ChatScope`` over the test app, with a fake
planner, a tool catalogue that discovers no server, and runs that finish inline."""

from __future__ import annotations

from fastapi import FastAPI
from langchain_core.tools import BaseTool

from api.db import Database
from api.models import User
from api.services import agent_tools
from api.services.agent_types import ToolDescriptor
from api.services.catalog import default_model_id
from api.services.chat_tools.scope import ChatScope
from api.services.llm import LLMProfile
from api.services.multiagent.contracts import StepAgent
from api.services.run_policy import run_policy
from api.services.run_recorder import utcnow
from api.services.runs import RunService
from api.services.schedules.service import ScheduleAccess
from llm.base import LLMProvider
from tests.conftest import FakeProvider, InlineRunExecutor

#: What the fake catalogue says the person's agents can use.
TOOLS = [ToolDescriptor("web_search", "Search the web", "AIMIx")]


class FakeCatalog:
    """The person's tools, without discovering any MCP server."""

    def __init__(self, database: Database, user: User) -> None:
        self.user = user

    def available_sync(self) -> list[ToolDescriptor]:
        return TOOLS


def chat_scope(
    app: FastAPI,
    user: User,
    planner: LLMProvider | None = None,
    agent: StepAgent | None = None,
) -> ChatScope:
    """The chat's scope for ``user``: ``planner`` answers the planner's prompts and
    ``agent`` runs the steps of the runs it starts (both a FakeProvider by default)."""
    database = app.state.database
    settings = agent_tools.get_settings()
    # The tools open their own session for each call; this one only carries the
    # account and the server's limits.
    with database.session() as placeholder:
        schedules = ScheduleAccess(
            placeholder,
            user,
            settings.schedules_max_per_user,
            utcnow(),
            run_policy(settings).limits,
        )
    steps = agent or FakeProvider()
    plans = planner or FakeProvider()
    return ChatScope(
        database,
        user,
        LLMProfile("openrouter", default_model_id()),
        RunService(database, InlineRunExecutor(), max_parallel_steps=1),
        lambda: steps,
        schedules,
        planner=lambda profile: plans,
        catalog=FakeCatalog,
    )


def by_name(tools: list[BaseTool]) -> dict[str, BaseTool]:
    return {item.name: item for item in tools}

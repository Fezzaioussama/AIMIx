"""Adapter that runs each saved pipeline step as a LangGraph agent."""

from __future__ import annotations

import asyncio

from api.db import Database
from api.models import User
from api.services.agent import AgentLimits, AgentToolset, LangGraphChatAgent
from api.services.agent_tools import built_in_tools
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.llm import get_agent_model
from api.services.mcp import connections
from config.settings import get_settings


class PipelineAgentGenerator:
    """Run each step with its model, role, and selected tool policy."""

    def __init__(self, database: Database, user: User) -> None:
        self._database = database
        self._user = user

    def execute(self, task: AgentTask) -> AgentOutcome:
        settings = get_settings()
        agent = LangGraphChatAgent(
            get_agent_model(task.model),
            AgentToolset(
                connections(settings.mcp_servers, settings.mcp_timeout_seconds),
                built_in_tools(self._database, self._user, lambda: self, include_run=False),
            ),
            AgentLimits(settings.agent_timeout_seconds, settings.agent_recursion_limit),
        )
        return asyncio.run(agent.reply(task))

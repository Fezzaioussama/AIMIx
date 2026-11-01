"""What the chat's tools act with, bound to the signed-in person (§5 D). The
collaborators come in here, so tests hand in a fake planner or tool catalogue."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from api.db import Database
from api.models import User
from api.services.agent_types import ToolDescriptor
from api.services.llm import LLMProfile, get_planner_provider
from api.services.multiagent.contracts import StepAgent
from api.services.runs import RunService
from api.services.schedules.service import ScheduleAccess
from api.services.tool_catalog import PipelineToolCatalog
from llm.base import LLMProvider


class ToolLister(Protocol):
    """The tools a person's agents can use (``tool_catalog.PipelineToolCatalog``)."""

    def available_sync(self) -> list[ToolDescriptor]: ...


@dataclass(frozen=True)
class ChatScope:
    """The person the chat acts for, their model profile, and the services its
    tools call: runs recorded like the Runs screen's, the agents a run's steps
    use, and their schedules."""

    database: Database
    user: User
    profile: LLMProfile
    runs: RunService
    agents: Callable[[], StepAgent]
    schedules: ScheduleAccess
    #: Builds the pipeline planner's provider, once a tool plans.
    planner: Callable[[LLMProfile], LLMProvider] = get_planner_provider
    #: The catalogue of what the person's agents can use.
    catalog: Callable[[Database, User], ToolLister] = PipelineToolCatalog

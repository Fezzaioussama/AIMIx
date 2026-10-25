"""Typed input and outcome for one pipeline agent step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from llm.usage import NO_USAGE, UNMETERED, TokenUsage, UsageMeter


@dataclass(frozen=True)
class AgentTask:
    prompt: str
    model: str
    role: str
    allowed_tools: list[str] | None
    #: What the agent must deliver; empty leaves the format to the prompt.
    expected_output: str = ""
    #: Hears each of the agent's model calls and may refuse one (a run's budget).
    meter: UsageMeter = field(default=UNMETERED, compare=False, repr=False)


@dataclass(frozen=True)
class ToolCallTrace:
    name: str
    status: Literal["success", "error"]


@dataclass(frozen=True)
class AgentOutcome:
    output: str
    tool_calls: list[ToolCallTrace]
    #: What the agent's model calls used, added up.
    usage: TokenUsage = NO_USAGE


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    source: str

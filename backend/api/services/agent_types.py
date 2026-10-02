"""Typed input and outcome for one pipeline agent step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AgentTask:
    prompt: str
    model: str
    role: str
    allowed_tools: list[str] | None


@dataclass(frozen=True)
class ToolCallTrace:
    name: str
    status: Literal["success", "error"]


@dataclass(frozen=True)
class AgentOutcome:
    output: str
    tool_calls: list[ToolCallTrace]


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    source: str

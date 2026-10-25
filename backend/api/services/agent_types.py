"""Typed input and outcome for one pipeline agent step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RunStepRef:
    """Which recorded run, and which of its steps, a task belongs to."""

    run_id: int
    step_order: int


@dataclass(frozen=True)
class AgentTask:
    prompt: str
    model: str
    role: str
    allowed_tools: list[str] | None
    #: What the agent must deliver; empty leaves the format to the prompt.
    expected_output: str = ""
    #: Where the task runs, so a tool that must ask the run's owner first can
    #: (approval gates); None outside a recorded run, where nobody can be asked.
    run_step: RunStepRef | None = None


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

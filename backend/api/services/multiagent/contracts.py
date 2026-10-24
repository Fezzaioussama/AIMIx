"""Small contracts shared by the pipeline graph and agent adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace


@dataclass(frozen=True)
class InputField:
    """A named value every run is given; step prompts insert it as ``{name}``."""

    name: str
    label: str = ""
    description: str = ""

    @property
    def display_label(self) -> str:
        return self.label.strip() or self.name


@dataclass(frozen=True)
class StepSpec:
    """Snapshot of a saved step; graph nodes never hold an ORM entity."""

    order: int
    stage: int
    title: str
    prompt: str
    model: str
    role: str
    allowed_tools: tuple[str, ...] | None
    is_output: bool
    expected_output: str = ""


@dataclass(frozen=True)
class PipelineSpec:
    pipeline_id: int | None
    name: str
    steps: tuple[StepSpec, ...]
    inputs: tuple[InputField, ...] = ()


@dataclass(frozen=True)
class RunInputs:
    """Where a run starts: the first stage's input, and the named values that
    every step, in any stage, can insert into its prompt."""

    text: str
    values: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StepResult:
    step_order: int
    stage: int
    title: str
    model: str
    input_used: str
    output: str
    is_output: bool = False
    tool_calls: list[ToolCallTrace] = field(default_factory=list)


@dataclass(frozen=True)
class RunResult:
    pipeline_name: str
    final_output: str
    intermediate_results: list[StepResult]


class StepAgent(Protocol):
    """Agent port; replace the LangGraph/MCP adapter without changing the graph."""

    async def execute(self, task: AgentTask) -> AgentOutcome: ...

"""Small contracts shared by the pipeline graph and agent adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from api.exceptions import DomainError
from api.services.agent_types import AgentOutcome, AgentTask, RunStepRef, ToolCallTrace


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


class StepEventKind(str, Enum):
    """A moment in one step's life, in the order the graph reports them."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class StepEvent:
    """What the graph tells a ``StepObserver`` about one step.

    Extend by adding an optional field (or a field on ``StepResult``, which an
    agent can fill through ``AgentOutcome``): the graph's control flow does not
    change, and observers ignore what they do not read.
    """

    kind: StepEventKind
    step: StepSpec
    #: The stage input the step was given.
    input_used: str
    #: Set when ``kind`` is SUCCEEDED.
    result: StepResult | None = None
    #: Set when ``kind`` is FAILED.
    error: DomainError | None = None


class StepObserver(Protocol):
    """Observer port: told of each step's progress while a run executes.

    The graph awaits every call before the step goes on, so an observer sees a
    step's events in order and may hold it back. An exception raised here fails
    the run.
    """

    async def on_step_event(self, event: StepEvent) -> None: ...


class _SilentObserver:
    """Null Object: the observer of a run that nobody follows."""

    async def on_step_event(self, event: StepEvent) -> None:
        return None


SILENT_OBSERVER: StepObserver = _SilentObserver()


@dataclass(frozen=True)
class RunControl:
    """How a run reports progress, and what an earlier attempt already finished."""

    observer: StepObserver = SILENT_OBSERVER
    #: Results of steps that already succeeded, by step order (a resumed run).
    #: They are reused as they are; their agents do not run again.
    completed: Mapping[int, StepResult] = field(default_factory=dict)
    #: The recorded run being executed; None for a run nobody records.
    run_id: int | None = None

    def step_ref(self, order: int) -> RunStepRef | None:
        """Where a step's task runs, for tools that must ask the run's owner first."""
        return None if self.run_id is None else RunStepRef(self.run_id, order)

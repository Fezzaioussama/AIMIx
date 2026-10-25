"""Builders shared by the conditional-step and review-loop tests: snapshot steps
in one line, a scripted step agent and an observer that remembers every event.

Nothing here waits for real or reaches a provider.
"""

from __future__ import annotations

import asyncio
import threading
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from api.exceptions import ProviderUnavailable
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.multiagent.conditions import StepCondition
from api.services.multiagent.contracts import (
    PipelineSpec,
    RunControl,
    RunInputs,
    RunResult,
    StepEvent,
    StepEventKind,
    StepSpec,
)
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.reviews import StepReview
from llm.usage import NO_USAGE, TokenUsage

REVISE = "VERDICT: REVISE"
PASS = "VERDICT: PASS"


def step(
    order: int,
    stage: int,
    role: str,
    prompt: str = "{input}",
    *,
    condition: StepCondition | None = None,
    review: StepReview | None = None,
    is_output: bool = False,
) -> StepSpec:
    """A snapshot step whose agent is found by ``role``."""
    return StepSpec(
        order=order,
        stage=stage,
        title=role.title(),
        prompt=prompt,
        model="m",
        role=role,
        allowed_tools=None,
        is_output=is_output,
        condition=condition,
        review=review,
    )


def spec(*steps: StepSpec) -> PipelineSpec:
    return PipelineSpec(pipeline_id=None, name="Flow", steps=tuple(steps))


def when(source: str, operator: str, value: str = "") -> StepCondition:
    return StepCondition(source, operator, value)


def review_to(stage: int, max_rounds: int = 2) -> StepReview:
    return StepReview(stage, max_rounds)


class ScriptedAgent:
    """Answers each step from its role's script: one answer per time the step
    runs, the last one repeating. A role without a script answers ``out-<role>``.

    ``calls`` lists ``(role, prompt)`` in the order the steps ran; ``fail`` maps
    a role to the (1-based) run of it that raises a provider error; ``usage``
    is what every model call of a step reports to its meter. ``hold`` maps a
    role to the run of it that waits (``entered`` is set when it does) until
    ``release`` is set or the run is stopped (``stopped`` then lists its role).
    """

    def __init__(
        self,
        script: Mapping[str, Sequence[str]] | None = None,
        fail: Mapping[str, int] | None = None,
        usage: TokenUsage = NO_USAGE,
        hold: Mapping[str, int] | None = None,
    ) -> None:
        self.script = {role: list(answers) for role, answers in (script or {}).items()}
        self.fail = dict(fail or {})
        self.usage = usage
        self.hold = dict(hold or {})
        self.entered = threading.Event()
        self.release = threading.Event()
        self.stopped: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self._runs: Counter[str] = Counter()

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self._runs[task.role] += 1
        self.calls.append((task.role, task.prompt))
        task.meter.before_call()
        await asyncio.sleep(0)
        task.meter.after_call(self.usage)
        if self.hold.get(task.role) == self._runs[task.role]:
            await self._held(task.role)
        if self.fail.get(task.role) == self._runs[task.role]:
            raise ProviderUnavailable(f"{task.role} failed")
        return AgentOutcome(self.answer(task.role), [], self.usage)

    async def _held(self, role: str) -> None:
        self.entered.set()
        try:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.stopped.append(role)
            raise

    def answer(self, role: str) -> str:
        answers = self.script.get(role)
        if not answers:
            return f"out-{role}"
        return answers[min(self._runs[role], len(answers)) - 1]

    def roles(self) -> list[str]:
        """The roles in the order their steps ran."""
        return [role for role, _ in self.calls]

    def prompts(self, role: str) -> list[str]:
        """Every prompt the role's step was given, in order."""
        return [prompt for who, prompt in self.calls if who == role]

    def runs(self, role: str) -> int:
        return self._runs[role]


class RecordingObserver:
    """Remembers every step event, in the order the graph reported it."""

    def __init__(self) -> None:
        self.events: list[StepEvent] = []

    async def on_step_event(self, event: StepEvent) -> None:
        self.events.append(event)

    def seen(self) -> list[tuple[str, StepEventKind, int]]:
        """``(role, kind, round)`` of each event."""
        return [(event.step.role, event.kind, event.round) for event in self.events]

    def of(self, role: str) -> list[tuple[StepEventKind, int]]:
        return [(kind, round_) for who, kind, round_ in self.seen() if who == role]


def run_flow(
    pipeline: PipelineSpec,
    agent: ScriptedAgent,
    text: str = "seed",
    values: Mapping[str, str] | None = None,
    control: RunControl | None = None,
) -> RunResult:
    """Run the snapshot to its end, in this process."""
    runner = GraphPipelineRunner(max_parallel_steps=4)
    return asyncio.run(runner.arun(pipeline, agent, RunInputs(text, values or {}), control))


def outputs_of(result: RunResult) -> dict[int, str]:
    return {item.step_order: item.output for item in result.intermediate_results}


def rounds_of(result: RunResult) -> dict[int, int]:
    return {item.step_order: item.rounds for item in result.intermediate_results}


def stored_step(
    order: int,
    stage: int,
    role: str,
    condition: dict[str, str] | None = None,
    review: dict[str, int] | None = None,
) -> dict[str, Any]:
    """A pipeline step as the repository stores it (prompt ``p<order> {input}``)."""
    return {
        "order": order,
        "stage": stage,
        "prompt": f"p{order} {{input}}",
        "model": "m",
        "role": role,
        "condition": condition,
        "review": review,
    }

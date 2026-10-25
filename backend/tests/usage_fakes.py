"""A step agent whose model calls report to the run's meter the way the real one
does, and the small builders the usage and budget tests share. No network."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from api.db import Database
from api.exceptions import ProviderUnavailable
from api.models import Pipeline, Run, User
from api.repositories import pipelines, runs
from api.repositories.pipelines import PipelineChanges
from api.services.agent_types import AgentOutcome, AgentTask
from llm.usage import NO_USAGE, TokenUsage

WAIT_SECONDS = 5.0

#: A cost that adds up exactly in binary floating point, so a limit can be hit
#: on the call that reaches it: eight of them are $0.50.
EXACT_COST = 0.0625


@dataclass(frozen=True)
class ModelCall:
    """What one model call used."""

    input_tokens: int = 100
    output_tokens: int = 50
    cost_usd: float | None = EXACT_COST

    @property
    def usage(self) -> TokenUsage:
        return TokenUsage.of(self.input_tokens, self.output_tokens, self.cost_usd)


class UsageAgent:
    """Each step makes ``calls[role]`` model calls (default 1), each one asking
    its meter first, then "in flight" while other steps run, then reported.

    ``reported`` lists the calls that finished and were reported, as
    ``(role, usage)``. ``fail`` roles raise a provider error after their calls;
    ``hold`` roles then wait to be released (or stopped).
    """

    def __init__(
        self,
        calls: dict[str, int] | None = None,
        call: ModelCall = ModelCall(),
        fail: tuple[str, ...] = (),
        hold: tuple[str, ...] = (),
    ) -> None:
        self.calls = calls or {}
        self.call = call
        self.fail = set(fail)
        self.hold = set(hold)
        self.release = threading.Event()
        self.reported: list[tuple[str, TokenUsage]] = []
        self.executed: list[str] = []

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.executed.append(task.role)
        used = NO_USAGE
        for _ in range(self.calls.get(task.role, 1)):
            task.meter.before_call()
            await asyncio.sleep(0)  # the call is in flight: parallel steps get their turn
            task.meter.after_call(self.call.usage)
            self.reported.append((task.role, self.call.usage))
            used += self.call.usage
        if task.role in self.hold:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
        if task.role in self.fail:
            self.fail.discard(task.role)
            raise ProviderUnavailable(f"{task.role} failed")
        return AgentOutcome(f"out-{task.role}", [], used)

    def reported_by(self, role: str) -> TokenUsage:
        return sum((usage for who, usage in self.reported if who == role), NO_USAGE)

    def reported_total(self) -> TokenUsage:
        return sum((usage for _, usage in self.reported), NO_USAGE)


def staged_pipeline(database: Database, owner: User, stages: list[int]) -> Pipeline:
    """Step ``n`` (from 1) has role ``role-n`` and runs in ``stages[n - 1]``."""
    steps = [
        {"order": n, "stage": stage, "prompt": f"p{n} {{input}}", "model": "m", "role": f"role-{n}"}
        for n, stage in enumerate(stages, start=1)
    ]
    with database.session() as session:
        return pipelines.create_with_steps(session, owner, PipelineChanges("Flow", steps=steps))


def load_run(database: Database, run_id: int) -> Run:
    with database.session() as session:
        run = runs.load(session, run_id)
    assert run is not None
    return run


def wait_for_run(database: Database, run_id: int, done: Callable[[Run], bool]) -> Run:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        run = load_run(database, run_id)
        if done(run):
            return run
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never got there: {load_run(database, run_id).status}")

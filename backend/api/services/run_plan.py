"""What a run is started with, how it is saved, and what one execution of it
needs, rebuilt from its own row: the snapshot, the inputs bound again, the
steps an earlier attempt finished, and its limits and spending so far.

Plain Python values in and out (AGENTS.md §2); ``services/runs`` uses them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from api.models import COMPLETED_STEP_STATUSES, Run, RunStep, RunTrigger, StepStatus
from api.repositories import runs as repository
from api.services.agent_types import ToolCallTrace
from api.services.multiagent.contracts import PipelineSpec, RunInputs, StepResult
from api.services.multiagent.graph import output_orders
from api.services.multiagent.mapper import spec_from_json, spec_to_json
from api.services.multiagent.reviews import Verdict
from api.services.pipeline_inputs import bind_run_inputs
from api.services.pipelines import PreparedRun
from api.services.run_budget import NO_BUDGET, RunBudget, run_budget
from api.services.usage import step_usage, total_usage
from llm.usage import TokenUsage


@dataclass(frozen=True)
class RunStart:
    """What a run is started with: free text, or a value per named input; its
    spending limits (a limit left unset takes the server's default); and what
    started it (``schedule_id`` names the schedule when one did)."""

    text: str = ""
    values: Mapping[str, str] = field(default_factory=dict)
    budget: RunBudget = NO_BUDGET
    trigger: RunTrigger = RunTrigger.MANUAL
    schedule_id: int | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    spec: PipelineSpec
    inputs: RunInputs
    completed: dict[int, StepResult]
    #: The review round each step's row was last in, by step order.
    rounds: dict[int, int]
    #: The run's limits, and what its earlier attempts already spent.
    budget: RunBudget
    spent: TokenUsage


def new_run(pipeline_id: int | None, prepared: PreparedRun, start: RunStart) -> repository.NewRun:
    """The row of a run of ``prepared``, queued with ``start``'s inputs and limits."""
    spec = prepared.spec
    outputs = output_orders(spec.steps)
    return repository.NewRun(
        pipeline_id=pipeline_id,
        pipeline_name=spec.name,
        definition=spec_to_json(spec),
        input_text=start.text,
        input_values=dict(start.values),
        trigger=start.trigger,
        schedule_id=start.schedule_id,
        steps=[
            {
                "step_order": step.order,
                "stage": step.stage,
                "title": step.title,
                "model": step.model,
                "is_output": step.order in outputs,
            }
            for step in spec.steps
        ],
        max_cost_usd=start.budget.max_cost_usd,
        max_tokens=start.budget.max_tokens,
    )


def _verdict(text: str | None) -> Verdict | None:
    try:
        return None if text is None else Verdict(text)
    except ValueError:
        return None


def _saved_result(step: RunStep) -> StepResult:
    """A succeeded or skipped step as the graph reported it, rebuilt from its row."""
    calls = [
        ToolCallTrace(call["name"], cast(Literal["success", "error"], call["status"]))
        for call in step.tool_calls
    ]
    return StepResult(
        step_order=step.step_order,
        stage=step.stage,
        title=step.title,
        model=step.model,
        input_used=step.input_used,
        output=step.output,
        is_output=step.is_output,
        tool_calls=calls,
        usage=step_usage(step),
        rounds=step.rounds,
        skipped=step.status == StepStatus.SKIPPED,
        verdict=_verdict(step.verdict),
    )


def plan_of(run: Run) -> ExecutionPlan:
    """What an execution of ``run`` needs, from the run's own row alone."""
    spec = spec_from_json(run.pipeline_id, run.definition)
    inputs = bind_run_inputs(spec.inputs, run.input_text, run.input_values)
    done = {
        step.step_order: _saved_result(step)
        for step in run.steps
        if step.status in COMPLETED_STEP_STATUSES
    }
    rounds = {step.step_order: step.rounds for step in run.steps}
    return ExecutionPlan(spec, inputs, done, rounds, run_budget(run), total_usage(run.steps))

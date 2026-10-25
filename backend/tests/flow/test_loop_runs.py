"""A review loop in a recorded run: what the rows hold, what the rounds cost, a
spending limit and an approval inside a round, and stopping the run mid-loop."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError as FutureCancelledError

import pytest

from api.db import Database
from api.models import ApprovalStatus, Run, RunStatus, StepStatus, User
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.approvals.decisions import ApprovalAnswer
from api.services.approvals.gate import RunApprovalGate, ToolRequest
from api.services.run_budget import RunBudget
from api.services.runs import RunService, RunStart
from llm.usage import TokenUsage
from tests.approval_fakes import ARGUMENTS, FAST_LIMITS, recording_tool
from tests.flow.fakes import PASS, REVISE, ScriptedAgent
from tests.flow.support import WAIT_SECONDS, load, review_team, rounds, row, statuses, wait_for

CALL = TokenUsage.of(100, 50, 0.0625)


def test_a_loop_is_recorded_in_place_with_its_rounds_and_verdict(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent(
        {
            "writer": ["draft v1", "draft v2"],
            "reviewer": [f"Shorten the intro.\n{REVISE}", f"Good now.\n{PASS}"],
        }
    )

    started = service.start(owner, review_team(database, owner), RunStart("seed"), agent)
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    assert outcome.result is not None
    run = load(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert statuses(run) == [StepStatus.SUCCEEDED] * 3
    assert rounds(run) == [1, 2, 2]
    writer, reviewer = row(run, 2), row(run, 3)
    assert writer.output == "draft v2"
    assert (reviewer.output, reviewer.verdict) == ("Good now.", "pass")
    assert (row(run, 1).verdict, writer.verdict) == (None, None)
    assert run.final_output == "Good now."
    # The row shows the newest round: the input the reviewer saw, and when it started.
    assert reviewer.input_used == "draft v2"
    assert reviewer.finished_at is not None


def test_a_loop_that_ran_out_of_rounds_ends_the_run_with_the_last_verdict(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent({"reviewer": [f"Not yet.\n{REVISE}"]})
    pipeline = review_team(database, owner, max_rounds=1, publisher=True)

    started = service.start(owner, pipeline, RunStart("seed"), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    run = load(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED and run.error_code == ""
    assert rounds(run) == [1, 2, 2, 1]
    assert (row(run, 3).verdict, row(run, 3).output) == ("revise", "Not yet.")
    assert agent.prompts("publisher") == ["p4 Not yet."]


def test_what_each_round_used_adds_up_on_the_row(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]}, usage=CALL)

    started = service.start(owner, review_team(database, owner), RunStart("seed"), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    run = load(database, started.run.id)
    research, writer, reviewer = row(run, 1), row(run, 2), row(run, 3)
    assert (research.input_tokens, research.cost_usd) == (100, 0.0625)
    # Two rounds, two model calls: the row kept adding to what the first round spent.
    assert (writer.input_tokens, writer.output_tokens, writer.cost_usd) == (200, 100, 0.125)
    assert (reviewer.input_tokens, reviewer.cost_usd) == (200, 0.125)
    assert sum(step.input_tokens for step in run.steps) == 500


def test_a_spending_limit_stops_the_run_inside_a_round(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]}, usage=CALL)
    start = RunStart("seed", budget=RunBudget(max_cost_usd=0.25))

    started = service.start(owner, review_team(database, owner), start, agent)
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    assert outcome.error is not None
    run = load(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "budget_exceeded")
    # Four calls cost $0.25: the reviewer's second call (round 2) was refused.
    assert statuses(run) == [StepStatus.SUCCEEDED, StepStatus.SUCCEEDED, StepStatus.FAILED]
    assert rounds(run) == [1, 2, 2]
    reviewer = row(run, 3)
    assert reviewer.error_code == "budget_exceeded"
    assert (reviewer.input_tokens, reviewer.cost_usd) == (100, 0.0625)
    assert sum(step.cost_usd or 0 for step in run.steps) == 0.25
    # The reviewer did start its second round: its first model call was what was refused.
    assert agent.runs("reviewer") == 2


class AskingWriter(ScriptedAgent):
    """The writer asks its step's approval gate every time it runs, like an agent
    about to use a tool that must ask first."""

    def __init__(self, database: Database, script: dict[str, list[str]]) -> None:
        super().__init__(script)
        self._database = database

    async def execute(self, task: AgentTask) -> AgentOutcome:
        if task.role == "writer":
            assert task.run_step is not None
            gate = RunApprovalGate(self._database, task.run_step, FAST_LIMITS)
            await gate.ask(ToolRequest(recording_tool("crm_send_email", []), "crm", ARGUMENTS))
        return await super().execute(task)


def test_an_approval_asked_in_a_later_round_waits_for_its_own_answer(
    database: Database, owner: User, service: RunService
) -> None:
    agent = AskingWriter(database, {"reviewer": [REVISE, PASS]})
    started = service.start(owner, review_team(database, owner), RunStart("seed"), agent)

    def waiting_for_someone_new(seen: set[int]) -> Callable[[Run], bool]:
        return lambda run: (
            run.status == RunStatus.WAITING
            and len(run.pending_approvals) == 1
            and run.pending_approvals[0].id not in seen
        )

    first_wait = wait_for(database, started.run.id, waiting_for_someone_new(set()))
    [first] = first_wait.pending_approvals
    assert (first.step_order, row(first_wait, 2).rounds) == (2, 1)
    service.answer_approval(owner, ApprovalAnswer(first.run_id, first.id, ApprovalStatus.APPROVED))

    second_wait = wait_for(database, started.run.id, waiting_for_someone_new({first.id}))

    [second] = second_wait.pending_approvals
    assert second.step_order == 2
    # The writer is running its second round, and the reviewer still shows the first.
    assert (row(second_wait, 2).status, row(second_wait, 2).rounds) == (StepStatus.RUNNING, 2)
    assert (row(second_wait, 3).status, row(second_wait, 3).rounds) == (StepStatus.SUCCEEDED, 1)
    service.answer_approval(
        owner, ApprovalAnswer(second.run_id, second.id, ApprovalStatus.APPROVED)
    )
    started.finished.result(timeout=WAIT_SECONDS)
    done = load(database, started.run.id)
    assert (done.status, done.pending_approvals) == (RunStatus.SUCCEEDED, [])
    assert rounds(done) == [1, 2, 2]


def test_stopping_a_run_in_a_later_round_leaves_the_earlier_round_to_resume_from(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent({"reviewer": [f"Fix X.\n{REVISE}", PASS]}, hold={"writer": 2})
    started = service.start(owner, review_team(database, owner), RunStart("seed"), agent)
    assert agent.entered.wait(WAIT_SECONDS), "the second draft never started"

    stopped = service.cancel(owner, started.run.id)

    assert stopped.status == RunStatus.CANCELLED
    with pytest.raises(FutureCancelledError):
        started.finished.result(timeout=WAIT_SECONDS)
    run = load(database, started.run.id)
    # The writer was cancelled in its second round; the reviewer still holds round 1.
    assert statuses(run) == [StepStatus.SUCCEEDED, StepStatus.CANCELLED, StepStatus.SUCCEEDED]
    assert rounds(run) == [1, 2, 1]
    assert (row(run, 3).verdict, row(run, 3).output) == ("revise", "Fix X.")
    assert agent.stopped == ["writer"]

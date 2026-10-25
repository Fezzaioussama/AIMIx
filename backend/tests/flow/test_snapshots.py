"""The definition a run stores: conditions and reviews are part of it, and a run
saved before they existed (or holding odd data) must still load and resume."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from api.db import Database
from api.models import Pipeline, PipelineStep, RunStatus, StepStatus, User
from api.repositories import runs
from api.services.multiagent.conditions import StepCondition
from api.services.multiagent.mapper import snapshot_pipeline, spec_from_json, spec_to_json
from api.services.multiagent.reviews import StepReview
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService
from tests.flow.fakes import ScriptedAgent, review_to, spec, step, when
from tests.flow.support import load, wait_for

OLD_STEP = {
    "order": 1,
    "stage": 1,
    "title": "Only step",
    "prompt": "{input}",
    "model": "m",
    "role": "Writer",
    "allowed_tools": None,
    "is_output": True,
    "expected_output": "",
}


def stored(**fields: Any) -> dict[str, Any]:
    return {"name": "Stored", "inputs": [], "steps": [{**OLD_STEP, **fields}]}


def test_a_step_stores_its_condition_and_review_as_plain_json() -> None:
    pipeline = spec(
        step(1, 1, "a"),
        step(2, 2, "b", condition=when("input:topic", "contains", "bees")),
        step(3, 3, "c", review=review_to(2, 3)),
    )

    steps = spec_to_json(pipeline)["steps"]

    assert (steps[0]["condition"], steps[0]["review"]) == (None, None)
    assert steps[1]["condition"] == {
        "source": "input:topic",
        "operator": "contains",
        "value": "bees",
    }
    assert steps[2]["review"] == {"send_back_to_stage": 2, "max_rounds": 3}


def test_a_stored_snapshot_with_both_fields_rebuilds_the_same_pipeline() -> None:
    pipeline = spec(
        step(1, 1, "a"),
        step(2, 2, "b", condition=when("step:1", "not_empty")),
        step(3, 3, "c", review=review_to(1, 5)),
    )

    assert spec_from_json(None, spec_to_json(pipeline)) == pipeline


def test_a_snapshot_made_before_the_fields_existed_means_no_condition_and_no_review() -> None:
    [only] = spec_from_json(None, stored()).steps

    assert (only.condition, only.review) == (None, None)


@pytest.mark.parametrize(
    "fields",
    [
        {"condition": "garbage", "review": ["x"]},
        {"condition": {"source": "previous_output"}, "review": {"max_rounds": "many"}},
        {"condition": None, "review": {"send_back_to_stage": 1}},
    ],
)
def test_odd_stored_values_load_as_no_condition_and_no_review(fields: dict[str, Any]) -> None:
    [only] = spec_from_json(None, stored(**fields)).steps

    assert (only.condition, only.review) == (None, None)


def test_a_saved_pipeline_is_snapshotted_with_its_condition_and_review() -> None:
    pipeline = Pipeline(
        name="Saved",
        steps=[
            PipelineStep(order=1, stage=1, prompt="p", model="m"),
            PipelineStep(
                order=2,
                stage=2,
                prompt="p",
                model="m",
                condition={"source": "step:1", "operator": "equals", "value": " Yes "},
                review={"send_back_to_stage": 1, "max_rounds": 2},
            ),
        ],
    )

    first, second = snapshot_pipeline(pipeline).steps

    assert (first.condition, first.review) == (None, None)
    assert second.condition == StepCondition("step:1", "equals", "Yes")
    assert second.review == StepReview(1, 2)


@pytest.fixture
def second_executor() -> Iterator[BackgroundRunExecutor]:
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=2.0)
    yield background
    background.shutdown()


def test_a_run_saved_before_the_fields_existed_resumes(
    database: Database, owner: User, second_executor: BackgroundRunExecutor
) -> None:
    definition = {
        "name": "Old run",
        "inputs": [],
        "steps": [
            {**OLD_STEP, "order": 1, "stage": 1, "role": "first"},
            {**OLD_STEP, "order": 2, "stage": 2, "role": "second"},
        ],
    }
    rows = [
        {"step_order": n, "stage": n, "title": "", "model": "m", "is_output": n == 2}
        for n in (1, 2)
    ]
    new = runs.NewRun(None, "Old run", definition, "seed", {}, rows)
    with database.session() as session:
        run = runs.create(session, owner, new)
        done = frozenset({StepStatus.PENDING})
        runs.set_step(
            session,
            run.id,
            runs.StepChange(1, done, {"status": StepStatus.SUCCEEDED, "output": "kept"}),
        )
        runs.set_status(session, run.id, [RunStatus.QUEUED], {"status": RunStatus.INTERRUPTED})
    agent = ScriptedAgent()

    RunService(database, second_executor, max_parallel_steps=4).resume(owner, run.id, agent)
    finished = wait_for(database, run.id, lambda r: r.status == RunStatus.SUCCEEDED)

    assert agent.calls == [("second", "kept")]
    assert [s.status for s in finished.steps] == [StepStatus.SUCCEEDED] * 2
    assert load(database, run.id).final_output == "out-second"

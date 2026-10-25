"""Conditional steps in the graph: a step whose condition does not hold is skipped,
what a skipped step leaves behind, and where a condition reads its text from."""

from __future__ import annotations

from api.services.multiagent.contracts import RunControl, StepEventKind, StepResult
from tests.flow_fakes import (
    RecordingObserver,
    ScriptedAgent,
    outputs_of,
    run_flow,
    spec,
    step,
    when,
)

SKIPPED, STARTED, DONE = StepEventKind.SKIPPED, StepEventKind.STARTED, StepEventKind.SUCCEEDED


def test_a_step_whose_condition_does_not_hold_is_skipped_without_running() -> None:
    agent = ScriptedAgent()
    observer = RecordingObserver()
    only_blogs = step(2, 2, "seo", condition=when("previous_output", "contains", "blog"))

    result = run_flow(
        spec(step(1, 1, "research"), only_blogs),
        agent,
        control=RunControl(observer=observer),
    )

    assert agent.roles() == ["research"]
    assert observer.of("seo") == [(SKIPPED, 1)]
    skipped = result.intermediate_results[1]
    assert (skipped.skipped, skipped.output, skipped.tool_calls, skipped.verdict) == (
        True,
        "",
        [],
        None,
    )
    assert skipped.input_used == "out-research"
    event = next(e for e in observer.events if e.kind == SKIPPED)
    assert event.result == skipped


def test_a_step_whose_condition_holds_runs_like_any_other() -> None:
    agent = ScriptedAgent({"research": ["a post for the blog"]})
    only_blogs = step(2, 2, "seo", condition=when("previous_output", "contains", "BLOG"))
    observer = RecordingObserver()

    result = run_flow(
        spec(step(1, 1, "research"), only_blogs), agent, control=RunControl(observer=observer)
    )

    assert agent.roles() == ["research", "seo"]
    assert observer.of("seo") == [(STARTED, 1), (DONE, 1)]
    assert not result.intermediate_results[1].skipped


def test_a_stage_merges_only_the_steps_that_ran() -> None:
    agent = ScriptedAgent({"a": ["from a"], "c": ["from c"]})
    pipeline = spec(
        step(1, 1, "a"),
        step(2, 1, "b", condition=when("previous_output", "equals", "never")),
        step(3, 1, "c"),
        step(4, 2, "next"),
    )

    run_flow(pipeline, agent)

    # The skipped step leaves no empty section behind.
    assert agent.prompts("next") == [
        "## Output of step 1\n\nfrom a\n\n## Output of step 3\n\nfrom c"
    ]


def test_the_one_step_left_hands_its_output_on_unchanged() -> None:
    agent = ScriptedAgent({"a": ["from a"]})
    pipeline = spec(
        step(1, 1, "a"),
        step(2, 1, "b", condition=when("previous_output", "equals", "never")),
        step(3, 2, "next"),
    )

    run_flow(pipeline, agent)

    assert agent.prompts("next") == ["from a"]


def test_a_stage_where_every_step_is_skipped_hands_its_input_on_unchanged() -> None:
    agent = ScriptedAgent({"research": ["the facts"]})
    never = when("previous_output", "equals", "never")
    pipeline = spec(
        step(1, 1, "research"),
        step(2, 2, "x", condition=never),
        step(3, 2, "y", condition=never),
        step(4, 3, "next"),
    )

    run_flow(pipeline, agent)

    assert agent.roles() == ["research", "next"]
    assert agent.prompts("next") == ["the facts"]


def test_when_the_last_stage_is_skipped_the_run_ends_with_what_it_was_handed() -> None:
    agent = ScriptedAgent({"research": ["the facts"]})
    last = step(2, 2, "seo", condition=when("previous_output", "contains", "blog"))

    result = run_flow(spec(step(1, 1, "research"), last), agent)

    assert result.final_output == "the facts"


def test_a_skipped_step_is_never_one_of_the_pipelines_outputs() -> None:
    agent = ScriptedAgent()
    seo = step(2, 2, "seo", condition=when("previous_output", "equals", "never"), is_output=True)
    pipeline = spec(step(1, 1, "research", is_output=True), seo)

    result = run_flow(pipeline, agent)

    assert [(r.step_order, r.is_output) for r in result.intermediate_results] == [
        (1, True),
        (2, False),
    ]


def test_a_skipped_last_stage_does_not_leave_an_output_marker_on_it() -> None:
    agent = ScriptedAgent()
    last = step(2, 2, "seo", condition=when("previous_output", "equals", "never"))

    result = run_flow(spec(step(1, 1, "research"), last), agent)

    # Nothing is marked, so the last stage would be the output: but it did not run.
    assert [r.is_output for r in result.intermediate_results] == [False, False]


def test_the_previous_result_in_the_first_stage_is_the_text_the_run_started_with() -> None:
    agent = ScriptedAgent()
    first = step(1, 1, "first", condition=when("previous_output", "contains", "bees"))
    second = step(2, 1, "second", condition=when("previous_output", "contains", "wasps"))

    run_flow(spec(first, second), agent, text="All about bees")

    assert agent.roles() == ["first"]


def test_a_named_input_can_be_what_a_condition_looks_at() -> None:
    agent = ScriptedAgent()
    pipeline = spec(
        step(1, 1, "research"),
        step(2, 2, "blog", condition=when("input:channel", "equals", "Blog")),
        step(3, 2, "mail", condition=when("input:channel", "equals", "email")),
    )

    run_flow(pipeline, agent, text="## Channel\n\nblog", values={"channel": "blog"})

    assert agent.roles() == ["research", "blog"]


def test_a_condition_can_look_at_a_step_in_an_earlier_stage() -> None:
    agent = ScriptedAgent({"check": ["Risk: HIGH"]})
    pipeline = spec(
        step(1, 1, "check"),
        step(2, 2, "relay"),
        step(3, 3, "escalate", condition=when("step:1", "contains", "risk: high")),
        step(4, 3, "archive", condition=when("step:1", "contains", "risk: low")),
    )

    run_flow(pipeline, agent)

    assert agent.roles() == ["check", "relay", "escalate"]


def test_a_skipped_steps_output_is_empty_for_the_conditions_after_it() -> None:
    agent = ScriptedAgent()
    never = when("previous_output", "equals", "never")
    pipeline = spec(
        step(1, 1, "research"),
        step(2, 2, "optional", condition=never),
        step(3, 3, "after", condition=when("step:2", "is_empty")),
    )

    run_flow(pipeline, agent)

    assert agent.roles() == ["research", "after"]


def test_each_step_of_a_stage_judges_the_same_input() -> None:
    agent = ScriptedAgent({"research": ["bees and wasps"]})
    pipeline = spec(
        step(1, 1, "research"),
        step(2, 2, "bees", condition=when("previous_output", "contains", "bees")),
        step(3, 2, "ants", condition=when("previous_output", "contains", "ants")),
        step(4, 2, "wasps", condition=when("previous_output", "contains", "wasps")),
    )

    result = run_flow(pipeline, agent)

    assert agent.roles() == ["research", "bees", "wasps"]
    assert [r.skipped for r in result.intermediate_results] == [False, False, True, False]


def test_an_unreadable_condition_skips_the_step_rather_than_running_it_by_accident() -> None:
    agent = ScriptedAgent()
    odd = step(2, 2, "odd", condition=when("previous_output", "sounds_like", "x"))

    result = run_flow(spec(step(1, 1, "research"), odd), agent)

    assert agent.roles() == ["research"]
    assert result.intermediate_results[1].skipped


def test_a_skipped_step_a_resumed_run_kept_is_not_judged_or_started_again() -> None:
    agent = ScriptedAgent()
    observer = RecordingObserver()
    never = when("previous_output", "equals", "never")
    pipeline = spec(step(1, 1, "a"), step(2, 2, "b", condition=never), step(3, 3, "c"))
    earlier = {
        1: StepResult(1, 1, "A", "m", "seed", "kept output"),
        2: StepResult(2, 2, "B", "m", "kept output", "", skipped=True),
    }

    result = run_flow(pipeline, agent, control=RunControl(observer=observer, completed=earlier))

    assert agent.roles() == ["c"]
    assert observer.seen() == [("c", STARTED, 1), ("c", DONE, 1)]
    # The skipped step left nothing, so the last stage got what the stage before handed on.
    assert agent.prompts("c") == ["kept output"]
    assert outputs_of(result)[2] == ""

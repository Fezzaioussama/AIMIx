"""Review loops in the graph: a reviewer that sends the work back, the feedback the
steps it goes back to receive, and what is counted, over scripted agents."""

from __future__ import annotations

import asyncio

import pytest

from api.services.multiagent.contracts import (
    RunControl,
    RunInputs,
    RunResult,
    StepEventKind,
    StepSpec,
)
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.loops import find_loops, recursion_limit
from api.services.multiagent.reviews import Verdict
from tests.flow_fakes import (
    PASS,
    REVISE,
    RecordingObserver,
    ScriptedAgent,
    outputs_of,
    review_to,
    rounds_of,
    run_flow,
    spec,
    step,
    when,
)

RESEARCH = step(1, 1, "research")
WRITER = step(2, 2, "writer")
STARTED, AGAIN = StepEventKind.STARTED, StepEventKind.RESTARTED
DONE, SKIPPED = StepEventKind.SUCCEEDED, StepEventKind.SKIPPED


def reviewer(max_rounds: int = 2, to_stage: int = 2, stage: int = 3, order: int = 3) -> StepSpec:
    return step(order, stage, "reviewer", review=review_to(to_stage, max_rounds))


def verdicts(result: RunResult) -> dict[int, Verdict | None]:
    return {item.step_order: item.verdict for item in result.intermediate_results}


def test_a_reviewer_that_asks_for_fixes_once_sends_the_work_back_once() -> None:
    agent = ScriptedAgent(
        {
            "writer": ["draft v1", "draft v2"],
            "reviewer": [f"Shorten the intro.\n{REVISE}", f"Good now.\n{PASS}"],
        }
    )

    result = run_flow(spec(RESEARCH, WRITER, reviewer()), agent)

    assert agent.roles() == ["research", "writer", "reviewer", "writer", "reviewer"]
    assert outputs_of(result) == {1: "out-research", 2: "draft v2", 3: "Good now."}
    assert rounds_of(result) == {1: 1, 2: 2, 3: 2}
    assert verdicts(result) == {1: None, 2: None, 3: Verdict.PASS}
    assert result.final_output == "Good now."


def test_the_work_goes_back_with_its_original_input_and_the_reviewers_feedback() -> None:
    agent = ScriptedAgent(
        {
            "writer": ["draft v1", "draft v2"],
            "reviewer": [f"Shorten the intro.\n{REVISE}", PASS],
        }
    )

    run_flow(spec(RESEARCH, step(2, 2, "writer", "Write from {input}"), reviewer()), agent)

    first_draft, second_draft = agent.prompts("writer")
    assert first_draft == "Write from out-research"
    # The usual prompt, with the input the stage had the first time, plus the feedback.
    assert second_draft == (
        "Write from out-research\n\n"
        "Feedback from the reviewer (round 2 of 3):\n\nShorten the intro.\n\n"
        "Revise your work to fix what the reviewer found."
    )
    # The reviewer judges each new draft in turn.
    assert agent.prompts("reviewer") == ["draft v1", "draft v2"]


def test_a_reviewer_that_keeps_asking_is_followed_until_its_rounds_run_out() -> None:
    agent = ScriptedAgent({"reviewer": [f"Still not right.\n{REVISE}"], "publisher": ["published"]})
    pipeline = spec(RESEARCH, WRITER, reviewer(max_rounds=2), step(4, 4, "publisher"))

    result = run_flow(pipeline, agent)

    # 1 + max_rounds times, then on to the next stage: running out of rounds is not an error.
    assert agent.runs("writer") == 3 and agent.runs("reviewer") == 3
    assert agent.runs("research") == 1 and agent.runs("publisher") == 1
    assert rounds_of(result) == {1: 1, 2: 3, 3: 3, 4: 1}
    assert verdicts(result)[3] == Verdict.REVISE
    assert agent.prompts("publisher") == ["Still not right."]
    assert result.final_output == "published"


def test_each_round_the_writer_is_told_the_newest_feedback_only() -> None:
    agent = ScriptedAgent({"reviewer": [f"First note.\n{REVISE}", f"Second note.\n{REVISE}", PASS]})

    run_flow(spec(RESEARCH, WRITER, reviewer(max_rounds=3)), agent)

    _, second, third = agent.prompts("writer")
    assert "round 2 of 4):\n\nFirst note." in second
    assert "round 3 of 4):\n\nSecond note." in third and "First note." not in third


def test_work_that_passes_the_first_time_is_not_sent_back() -> None:
    agent = ScriptedAgent({"reviewer": [f"Perfect.\n{PASS}"]})

    result = run_flow(spec(RESEARCH, WRITER, reviewer()), agent)

    assert agent.roles() == ["research", "writer", "reviewer"]
    assert rounds_of(result) == {1: 1, 2: 1, 3: 1}
    assert outputs_of(result)[3] == "Perfect."
    assert verdicts(result)[3] == Verdict.PASS


def test_a_reviewer_that_gives_no_verdict_lets_the_work_through() -> None:
    agent = ScriptedAgent({"reviewer": ["Some thoughts, but no verdict."]})

    result = run_flow(spec(RESEARCH, WRITER, reviewer()), agent)

    assert agent.runs("writer") == 1
    assert verdicts(result)[3] is None
    assert outputs_of(result)[3] == "Some thoughts, but no verdict."


def test_a_verdict_line_in_a_step_that_is_not_a_reviewer_is_left_alone() -> None:
    agent = ScriptedAgent({"writer": [f"Draft.\n{REVISE}"]})

    result = run_flow(spec(RESEARCH, WRITER, step(3, 3, "editor")), agent)

    assert agent.runs("writer") == 1
    assert outputs_of(result)[2] == f"Draft.\n{REVISE}"
    assert verdicts(result)[2] is None


def test_the_observer_hears_each_step_start_again_in_its_round() -> None:
    observer = RecordingObserver()
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]})

    run_flow(spec(RESEARCH, WRITER, reviewer()), agent, control=RunControl(observer=observer))

    assert observer.of("research") == [(STARTED, 1), (DONE, 1)]
    assert observer.of("writer") == [(STARTED, 1), (DONE, 1), (AGAIN, 2), (DONE, 2)]
    assert observer.of("reviewer") == [(STARTED, 1), (DONE, 1), (AGAIN, 2), (DONE, 2)]
    again = next(event for event in observer.events if event.kind == AGAIN)
    assert again.input_used == "out-research"
    last_review = [e.result for e in observer.events if e.step.role == "reviewer"][-1]
    assert last_review is not None
    assert (last_review.verdict, last_review.rounds) == (Verdict.PASS, 2)


def test_every_step_of_the_stage_the_work_went_back_to_receives_the_feedback() -> None:
    agent = ScriptedAgent({"reviewer": [f"Mind the tone.\n{REVISE}", PASS]})
    pipeline = spec(
        RESEARCH,
        step(2, 2, "draft"),
        step(3, 2, "outline"),
        step(4, 3, "merge", "Merge: {input}"),
        reviewer(to_stage=2, stage=4, order=5),
    )

    run_flow(pipeline, agent)

    for role in ("draft", "outline"):
        again = agent.prompts(role)[1]
        assert "Feedback from the reviewer (round 2 of 3):\n\nMind the tone." in again
    # A stage in between just consumes the redone work: it is not told to act on the feedback.
    merge = agent.prompts("merge")
    assert "Feedback" not in merge[1] and merge[1].startswith("Merge: ## Output of step 2")


def test_a_prompt_that_places_the_feedback_itself_does_not_get_it_twice() -> None:
    agent = ScriptedAgent({"reviewer": [f"Too long.\n{REVISE}", PASS]})
    writer = step(2, 2, "writer", "Draft from {input}. Reviewer said: [{feedback}]")

    run_flow(spec(RESEARCH, writer, reviewer()), agent)

    first, second = agent.prompts("writer")
    assert first == "Draft from out-research. Reviewer said: []"
    assert second == "Draft from out-research. Reviewer said: [Too long.]"


def test_an_empty_review_still_tells_the_writer_it_was_sent_back() -> None:
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]})

    run_flow(spec(RESEARCH, WRITER, reviewer()), agent)

    assert "The reviewer asked for another round but gave no details." in agent.prompts("writer")[1]


def test_a_loop_back_to_the_first_stage_starts_from_the_run_text_again() -> None:
    agent = ScriptedAgent({"reviewer": [f"Redo.\n{REVISE}", PASS]})
    writer = step(1, 1, "writer", "Write about {input}")

    run_flow(spec(writer, reviewer(to_stage=1, stage=2, order=2)), agent, text="bees")

    first, second = agent.prompts("writer")
    assert first == "Write about bees"
    assert second.startswith("Write about bees\n\nFeedback from the reviewer (round 2 of 3)")


def test_named_inputs_survive_a_loop_to_the_first_stage() -> None:
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]})
    writer = step(1, 1, "writer", "About {topic}")

    run_flow(
        spec(writer, reviewer(to_stage=1, stage=2, order=2)),
        agent,
        text="## Topic\n\nbees",
        values={"topic": "bees"},
    )

    assert agent.prompts("writer")[1].startswith("About bees")
    assert agent.prompts("reviewer") == ["out-writer", "out-writer"]


def test_a_reviewer_can_share_its_stage_with_another_step() -> None:
    agent = ScriptedAgent({"reviewer": [f"Fix it.\n{REVISE}", f"All good.\n{PASS}"]})
    pipeline = spec(RESEARCH, WRITER, reviewer(), step(4, 3, "checker"), step(5, 4, "final"))

    result = run_flow(pipeline, agent)

    assert agent.runs("checker") == 2 and agent.runs("final") == 1
    assert rounds_of(result) == {1: 1, 2: 2, 3: 2, 4: 2, 5: 1}
    # The next stage gets both outputs of the stage, without the verdict line.
    assert agent.prompts("final") == [
        "## Output of step 3\n\nAll good.\n\n## Output of step 4\n\nout-checker"
    ]


def test_two_separate_loops_each_count_their_own_rounds() -> None:
    agent = ScriptedAgent({"qa": [REVISE, PASS], "legal": [REVISE, REVISE, PASS]})
    pipeline = spec(
        step(1, 1, "draft"),
        step(2, 2, "qa", review=review_to(1, 1)),
        step(3, 3, "polish"),
        step(4, 4, "legal", review=review_to(3, 2)),
    )

    result = run_flow(pipeline, agent)

    assert agent.roles() == [
        *("draft", "qa", "draft", "qa"),
        *("polish", "legal", "polish", "legal", "polish", "legal"),
    ]
    assert rounds_of(result) == {1: 2, 2: 2, 3: 3, 4: 3}


def test_the_longest_loop_finishes_within_the_graphs_step_limit() -> None:
    agent = ScriptedAgent({"reviewer": [REVISE]})
    pipeline = spec(
        step(1, 1, "a"),
        step(2, 2, "b"),
        step(3, 3, "c"),
        step(4, 4, "d"),
        step(5, 5, "reviewer", review=review_to(1, 5)),
    )

    result = run_flow(pipeline, agent)

    assert agent.runs("a") == 6 and agent.runs("reviewer") == 6
    assert rounds_of(result) == {1: 6, 2: 6, 3: 6, 4: 6, 5: 6}


def test_the_step_limit_grows_with_the_rounds_a_loop_may_add() -> None:
    steps = [step(1, 1, "a"), step(2, 2, "b"), step(3, 3, "c", review=review_to(2, 3))]
    loops = find_loops([[item] for item in steps])

    assert recursion_limit(3, []) == 8
    # Each of the 3 rounds redoes stages 2 and 3 (a node and a join each) and goes back once.
    assert recursion_limit(3, loops) == 8 + 3 * (2 * 2 + 1)


def test_a_review_that_cannot_work_is_ignored_and_the_run_still_ends() -> None:
    agent = ScriptedAgent({"reviewer": [REVISE]})
    # It "sends the work back" to its own stage: data nobody validated must never
    # make a loop that does not end.
    broken = step(2, 2, "reviewer", review=review_to(2, 3))

    result = run_flow(spec(RESEARCH, broken), agent)

    assert agent.runs("reviewer") == 1
    assert verdicts(result)[2] == Verdict.REVISE


def test_overlapping_loops_are_cut_down_to_the_first_one() -> None:
    steps = [
        step(1, 1, "a"),
        step(2, 2, "b", review=review_to(1, 1)),
        step(3, 3, "c", review=review_to(2, 1)),
    ]

    loops = find_loops([[item] for item in steps])

    assert [loop.reviewer for loop in loops] == [2]


def test_a_condition_is_judged_again_each_round_and_a_step_can_start_running() -> None:
    agent = ScriptedAgent(
        {
            "writer": ["short draft", "a long draft"],
            "reviewer": [REVISE, PASS],
            "polish": ["polished"],
        }
    )
    polish = step(3, 3, "polish", condition=when("step:2", "contains", "long"))
    pipeline = spec(RESEARCH, WRITER, polish, step(4, 4, "reviewer", review=review_to(2, 1)))
    observer = RecordingObserver()

    result = run_flow(pipeline, agent, control=RunControl(observer=observer))

    # Round 1 skipped it (the stage handed its input on); round 2 ran it.
    assert observer.of("polish") == [(SKIPPED, 1), (AGAIN, 2), (DONE, 2)]
    assert agent.prompts("reviewer") == ["short draft", "polished"]
    assert rounds_of(result)[3] == 2
    assert not result.intermediate_results[2].skipped


def test_a_condition_can_also_skip_a_step_that_ran_the_round_before() -> None:
    agent = ScriptedAgent({"writer": ["short draft", "a long draft"], "reviewer": [REVISE, PASS]})
    polish = step(3, 3, "polish", condition=when("step:2", "not_contains", "long"))
    pipeline = spec(RESEARCH, WRITER, polish, step(4, 4, "reviewer", review=review_to(2, 1)))
    observer = RecordingObserver()

    result = run_flow(pipeline, agent, control=RunControl(observer=observer))

    assert observer.of("polish") == [(STARTED, 1), (DONE, 1), (SKIPPED, 2)]
    polished = result.intermediate_results[2]
    assert (polished.skipped, polished.output, polished.rounds) == (True, "", 2)
    assert agent.prompts("reviewer") == ["out-polish", "a long draft"]


def test_stopping_the_run_during_a_round_cancels_that_step() -> None:
    observer = RecordingObserver()
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]}, hold={"writer": 2})

    async def scenario() -> None:
        runner = GraphPipelineRunner(max_parallel_steps=2)
        job = asyncio.create_task(
            runner.arun(
                spec(RESEARCH, WRITER, reviewer()),
                agent,
                RunInputs("seed"),
                RunControl(observer=observer),
            )
        )
        for _ in range(500):
            if agent.entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert agent.entered.is_set(), "the second draft never started"
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job

    asyncio.run(scenario())

    assert agent.stopped == ["writer"]
    assert observer.of("writer") == [
        (STARTED, 1),
        (DONE, 1),
        (AGAIN, 2),
        (StepEventKind.CANCELLED, 2),
    ]
    # The reviewer never reached its second round.
    assert observer.of("reviewer") == [(STARTED, 1), (DONE, 1)]

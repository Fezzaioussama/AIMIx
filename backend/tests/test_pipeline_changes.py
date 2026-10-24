"""The change list a revision is reviewed with: how steps are paired, which
fields count as changed, and what is left out as noise."""

from __future__ import annotations

import copy
from typing import Any

from api.services.pipeline_changes import PipelineChange, diff_pipelines

Summary = tuple[str, str, str, int | None, tuple[str, ...]]


def step(order: int, title: str = "", **fields: Any) -> dict[str, Any]:
    """A saved-looking step; its prompt follows its title unless given."""
    return {
        "order": order,
        "stage": order,
        "title": title,
        "role": "",
        "allowed_tools": None,
        "is_output": False,
        "expected_output": "",
        "prompt": f"Do the {title or 'work'}: {{input}}",
        "model": "vendor/model",
        **fields,
    }


def pipeline(*steps: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {"name": "Launch kit", "inputs": [], "steps": list(steps), **fields}


def summary(changes: list[PipelineChange]) -> list[Summary]:
    return [(c.target, c.kind, c.label, c.order, c.fields) for c in changes]


def test_an_identical_pipeline_has_no_changes() -> None:
    original = pipeline(step(1, "Research"), step(2, "Draft"))
    assert diff_pipelines(original, copy.deepcopy(original)) == []


def test_spacing_and_tool_order_are_not_changes() -> None:
    original = pipeline(step(1, "Research", prompt="Find facts", allowed_tools=["a", "b"]))
    revised = pipeline(step(1, "Research", prompt="  Find facts\n", allowed_tools=["b", "a"]))
    assert diff_pipelines(original, revised) == []


def test_a_changed_step_names_its_fields_in_a_fixed_order() -> None:
    original = pipeline(step(1, "Research"), step(2, "Draft"))
    revised = pipeline(
        step(1, "Research", allowed_tools=["web_search"], model="vendor/other", prompt="New"),
        step(2, "Draft"),
    )
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "Research", 1, ("prompt", "model", "allowed_tools")),
    ]


def test_no_tools_and_every_tool_are_different_policies() -> None:
    original = pipeline(step(1, "Research", allowed_tools=[]))
    revised = pipeline(step(1, "Research", allowed_tools=None))
    assert diff_pipelines(original, revised)[0].fields == ("allowed_tools",)


def test_steps_are_paired_by_title_when_a_step_is_inserted_before_them() -> None:
    original = pipeline(step(1, "Research"), step(2, "Draft"))
    revised = pipeline(
        step(1, "Fact check"),
        step(2, "research ", prompt="Find {input} with sources"),
        step(3, "Draft"),
    )
    # The new first stage renumbers every later one; that alone is not a move.
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "added", "Fact check", 1, ()),
        ("step", "changed", "research", 2, ("title", "prompt")),
    ]


def test_a_renamed_step_is_paired_by_its_prompt() -> None:
    original = pipeline(step(1, "Research", prompt="Find facts"), step(2, "Draft"))
    revised = pipeline(step(1, "Intro"), step(2, "Facts", prompt="Find facts"), step(3, "Draft"))
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "added", "Intro", 1, ()),
        ("step", "changed", "Facts", 2, ("title",)),
    ]


def test_untitled_steps_fall_back_to_their_position() -> None:
    original = pipeline(step(1, prompt="a"), step(2, prompt="b"))
    revised = pipeline(step(1, prompt="a, shorter"), step(2, prompt="b"))
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "Step 1", 1, ("prompt",)),
    ]


def test_a_removed_step_is_listed_last_with_its_original_order() -> None:
    original = pipeline(step(1, "Research"), step(2, "Outline"), step(3, "Draft"))
    revised = pipeline(step(1, "Research"), step(2, "Draft", stage=2), step(3, "Summary"))
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "added", "Summary", 3, ()),
        ("step", "removed", "Outline", 2, ()),
    ]


def test_making_steps_parallel_lists_only_the_step_that_moved() -> None:
    original = pipeline(step(1, "Research A"), step(2, "Research B"), step(3, "Report"))
    revised = pipeline(
        step(1, "Research A"), step(2, "Research B", stage=1), step(3, "Report", stage=2)
    )
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "Research B", 2, ("stage",)),
    ]


def test_moving_a_step_earlier_lists_it_alone() -> None:
    original = pipeline(step(1, "Plan"), step(2, "Draft"), step(3, "Images"))
    revised = pipeline(step(1, "Plan"), step(2, "Images", stage=1), step(3, "Draft", stage=2))
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "Images", 2, ("stage",)),
    ]


def test_closing_a_gap_between_stages_is_not_a_move() -> None:
    original = pipeline(step(1, "Research"), step(2, "Draft", stage=5))
    revised = pipeline(step(1, "Research"), step(2, "Draft", stage=2))
    assert diff_pipelines(original, revised) == []


def test_two_steps_with_one_title_pair_in_order() -> None:
    original = pipeline(step(1, "Post", prompt="a"), step(2, "Post", prompt="b"))
    revised = pipeline(step(1, "Post", prompt="a"), step(2, "Post", prompt="b, longer"))
    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "Post", 2, ("prompt",)),
    ]


def test_input_changes_are_paired_by_name() -> None:
    topic = {"name": "topic", "label": "Topic", "description": ""}
    tone = {"name": "tone", "label": "Tone", "description": ""}
    original = pipeline(step(1, "Draft"), inputs=[topic, tone])
    revised = pipeline(
        step(1, "Draft"),
        inputs=[
            {**topic, "description": "What to write about"},
            {"name": "audience", "label": "Audience", "description": ""},
        ],
    )
    assert summary(diff_pipelines(original, revised)) == [
        ("input", "changed", "topic", None, ("description",)),
        ("input", "added", "audience", None, ()),
        ("input", "removed", "tone", None, ()),
    ]


def test_a_rename_comes_first() -> None:
    original = pipeline(step(1, "Draft"))
    revised = pipeline(step(1, "Draft", is_output=True), name="Launch kit v2")
    assert summary(diff_pipelines(original, revised)) == [
        ("pipeline", "changed", "Launch kit v2", None, ("name",)),
        ("step", "changed", "Draft", 1, ("is_output",)),
    ]


def test_malformed_planner_data_is_compared_without_failing() -> None:
    original = pipeline(step(1, "Draft"))
    revised = {"name": 7, "inputs": "none", "steps": ["junk", {"order": True, "title": "Draft"}]}
    # Only the step's title survived, so everything else reads as changed.
    missing = ("role", "prompt", "expected_output", "model", "is_output")
    assert summary(diff_pipelines(original, revised)) == [
        ("pipeline", "changed", "", None, ("name",)),
        ("step", "changed", "Draft", 1, missing),
    ]

"""What a revision changed, for people to review before they apply it.

Pure functions over plain pipeline data (the pipeline contract's fields as
dicts), so they are tested on their own and can compare any two versions.

How the two versions are lined up:

- **Steps** are paired before they are compared, trying in turn (``STEP_MATCHERS``):
  a step that did not change at all, then the same title (ignoring case and
  spacing), then the same prompt, then the same position in the list. Each step
  pairs at most once, the earliest candidate first. A revised step left unpaired
  was added; an original one left unpaired was removed.
- **Stages** are compared by where a step runs, not by their numbers: a paired
  step counts as moved (its ``stage`` changed) when its stage's rank among the
  paired steps' stages changed *and* it no longer runs before, alongside or after
  some other paired step as it did. So renumbered stages, stages added or removed
  with their own steps, and steps only shifted by another step's move are not
  reported. Making "Research B" run alongside "Research A" lists B alone.
- **Inputs** are paired by name, so a renamed input reads as removed plus added.
- Text is compared without surrounding whitespace, and tool lists in any order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

ChangeTarget = Literal["pipeline", "input", "step"]
ChangeKind = Literal["added", "removed", "changed"]
Item = Mapping[str, Any]

#: The step fields a change can name, in the order it lists them.
STEP_FIELDS = (
    "title",
    "role",
    "prompt",
    "expected_output",
    "model",
    "allowed_tools",
    "stage",
    "is_output",
)
#: The input fields a change can name; an input's name is its identity.
INPUT_FIELDS = ("label", "description")


@dataclass(frozen=True)
class PipelineChange:
    """One difference between a pipeline and its revision (§7 Value Object)."""

    target: ChangeTarget
    kind: ChangeKind
    #: The pipeline's new name, the input's name, or the step's title ("Step N"
    #: when it has none).
    label: str
    #: A step's order: in the revision when added or changed, in the original
    #: when removed. None for the pipeline and its inputs.
    order: int | None = None
    #: For a change, the fields that differ, in ``STEP_FIELDS`` / ``INPUT_FIELDS`` order.
    fields: tuple[str, ...] = ()


def diff_pipelines(before: Item, after: Item) -> list[PipelineChange]:
    """Every difference from ``before`` to ``after``: the name, then the inputs,
    then the steps, each in the revision's order with removals last."""
    return [
        *_name_changes(before, after),
        *_input_changes(_items(before, "inputs"), _items(after, "inputs")),
        *_step_changes(_items(before, "steps"), _items(after, "steps")),
    ]


def _items(pipeline: Item, key: str) -> list[Item]:
    value = pipeline.get(key)
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _words(value: object) -> str | None:
    """Text as matched: case and spacing ignored; None when there is none."""
    return " ".join(_text(value).split()).casefold() or None


def _comparable(value: object) -> object:
    """A field as compared: text without surrounding whitespace, a list in any order."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return tuple(sorted(str(item) for item in value))
    return value


def _differing(old: Item, new: Item, fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        name for name in fields if _comparable(old.get(name)) != _comparable(new.get(name))
    )


def _name_changes(before: Item, after: Item) -> list[PipelineChange]:
    old, new = _text(before.get("name")), _text(after.get("name"))
    return [] if old == new else [PipelineChange("pipeline", "changed", new, fields=("name",))]


def _input_changes(before: list[Item], after: list[Item]) -> list[PipelineChange]:
    old = {_text(item.get("name")): item for item in before}
    new = {_text(item.get("name")): item for item in after}
    changes: list[PipelineChange] = []
    for name, item in new.items():
        if name not in old:
            changes.append(PipelineChange("input", "added", name))
        elif fields := _differing(old[name], item, INPUT_FIELDS):
            changes.append(PipelineChange("input", "changed", name, fields=fields))
    changes.extend(PipelineChange("input", "removed", name) for name in old if name not in new)
    return changes


# --- Steps -----------------------------------------------------------------

StepKey = Callable[[int, Item], object]


def _content_key(position: int, step: Item) -> object:
    return tuple(_comparable(step.get(name)) for name in STEP_FIELDS)


def _title_key(position: int, step: Item) -> object:
    return _words(step.get("title"))


def _prompt_key(position: int, step: Item) -> object:
    return _words(step.get("prompt"))


def _position_key(position: int, step: Item) -> object:
    return position


#: How a revised step finds the step it came from, tried in this order (§7
#: Strategy). A key of None (a step without a title, say) never matches.
STEP_MATCHERS: tuple[StepKey, ...] = (_content_key, _title_key, _prompt_key, _position_key)


def _pair_steps(before: list[Item], after: list[Item]) -> dict[int, int]:
    """Map each revised step's index to the index of the step it came from."""
    pairs: dict[int, int] = {}
    for key in STEP_MATCHERS:
        free = [index for index in range(len(before)) if index not in pairs.values()]
        for index, step in enumerate(after):
            wanted = None if index in pairs else key(index, step)
            source = next(
                (i for i in free if wanted is not None and key(i, before[i]) == wanted), None
            )
            if source is not None:
                pairs[index] = source
                free.remove(source)
    return pairs


def _whole(value: object) -> int | None:
    """An integer field's value; None for anything else, booleans included."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _stage(step: Item) -> int:
    return _whole(step.get("stage")) or 0


def _ranks(steps: list[Item], indexes: list[int]) -> list[int]:
    """Each listed step's stage as its rank among the listed steps' stages, from 1."""
    stages = sorted({_stage(steps[index]) for index in indexes})
    return [stages.index(_stage(steps[index])) + 1 for index in indexes]


def _places(steps: list[Item], indexes: list[int]) -> list[tuple[int, ...]]:
    """For each listed step, whether it runs before (-1), alongside (0) or after (1)
    each of the listed steps."""
    stages = [_stage(steps[index]) for index in indexes]
    return [tuple((own > other) - (own < other) for other in stages) for own in stages]


def _moved_steps(before: list[Item], after: list[Item], pairs: dict[int, int]) -> set[int]:
    """Revised steps that now run at another point: their stage's rank among the
    paired steps changed, and so did whether they run before, alongside or after
    some other paired step. Requiring both leaves out renumbered stages, added or
    removed stages, and steps that were only shifted by another step's move."""
    revised = list(pairs)
    original = [pairs[index] for index in revised]
    old_ranks, new_ranks = _ranks(before, original), _ranks(after, revised)
    old_places, new_places = _places(before, original), _places(after, revised)
    return {
        index
        for position, index in enumerate(revised)
        if old_ranks[position] != new_ranks[position]
        and old_places[position] != new_places[position]
    }


def _changed_fields(old: Item, new: Item, moved: bool) -> tuple[str, ...]:
    """The step fields that differ. A stage number alone says little, so "stage"
    is listed when the step moved (``_moved_steps``)."""
    return tuple(
        name
        for name in STEP_FIELDS
        if (moved if name == "stage" else _comparable(old.get(name)) != _comparable(new.get(name)))
    )


def _step_change(
    kind: ChangeKind, step: Item, position: int, fields: tuple[str, ...] = ()
) -> PipelineChange:
    order = _whole(step.get("order"))
    number = position + 1 if order is None else order
    label = _text(step.get("title")) or f"Step {number}"
    return PipelineChange("step", kind, label, number, fields)


def _step_changes(before: list[Item], after: list[Item]) -> list[PipelineChange]:
    pairs = _pair_steps(before, after)
    moved = _moved_steps(before, after, pairs)
    changes: list[PipelineChange] = []
    for index, step in enumerate(after):
        if index not in pairs:
            changes.append(_step_change("added", step, index))
        elif fields := _changed_fields(before[pairs[index]], step, index in moved):
            changes.append(_step_change("changed", step, index, fields))
    paired = set(pairs.values())
    changes.extend(
        _step_change("removed", step, index)
        for index, step in enumerate(before)
        if index not in paired
    )
    return changes

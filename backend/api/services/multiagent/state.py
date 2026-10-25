"""What the pipeline graph carries from node to node (§6: no state outside it)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, TypedDict, TypeVar

from api.services.multiagent.contracts import StepResult

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class LoopState:
    """Where one review loop stands (§7 Value Object)."""

    #: How many times its reviewer has sent the work back so far.
    sent_back: int = 0
    #: What the reviewer said when it last sent the work back; "" before that.
    feedback: str = ""


NO_PROGRESS = LoopState()


def merge_dicts(existing: dict[K, V], update: dict[K, V]) -> dict[K, V]:
    """The reducer of every dictionary channel: an update adds or replaces entries."""
    return {**existing, **update}


class GraphState(TypedDict):
    #: What the stage about to run (or running) was handed.
    current_input: str
    #: The run's named inputs; set once, never written by a node.
    values: dict[str, str]
    #: The newest result of every step that has run, by step order.
    results: Annotated[dict[int, StepResult], merge_dicts]
    #: What each stage was handed, by the stage's position (from 0), so a review
    #: loop can start a stage over with the input it had.
    stage_inputs: Annotated[dict[int, str], merge_dicts]
    #: Where each review loop stands, by its reviewer's step order.
    loops: Annotated[dict[int, LoopState], merge_dicts]


class GraphUpdate(TypedDict, total=False):
    current_input: str
    results: dict[int, StepResult]
    stage_inputs: dict[int, str]
    loops: dict[int, LoopState]

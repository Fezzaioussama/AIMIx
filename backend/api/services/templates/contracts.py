"""What a mission template is, as immutable data (AGENTS.md §7 Value Object).

A template never names a model: when it is used, every step gets its owner's
default model, and only the tools its owner can use (see ``use.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from api.services.toolbox.tools import FETCH_URL, WEB_SEARCH

#: The gallery's filters, in no particular order; the API lists templates in
#: registry order and the gallery shows categories as they first appear.
Category = Literal["Research", "Documents", "Data", "Marketing"]

#: Reading the web: search, then open the pages worth reading.
WEB_RESEARCH = (WEB_SEARCH, FETCH_URL)


@dataclass(frozen=True)
class TemplateInput:
    """A named value every run is given; step prompts insert it as ``{name}``."""

    name: str
    label: str
    description: str


@dataclass(frozen=True)
class TemplateStep:
    """One agent of a template.

    ``tools`` names built-in tools, kept at use time only when the owner has
    them; ``()`` grants none and ``None`` would grant every available tool.
    """

    title: str
    role: str
    prompt: str
    expected_output: str
    stage: int
    tools: tuple[str, ...] | None = ()
    is_output: bool = False

    def as_plan(self) -> dict[str, Any]:
        """The step shaped like a planner's step: no order or model yet."""
        return {
            "stage": self.stage,
            "title": self.title,
            "role": self.role,
            "prompt": self.prompt,
            "expected_output": self.expected_output,
            "is_output": self.is_output,
            "allowed_tools": None if self.tools is None else list(self.tools),
        }


@dataclass(frozen=True)
class MissionTemplate:
    slug: str
    title: str
    category: Category
    #: One line for the gallery card.
    description: str
    inputs: tuple[TemplateInput, ...]
    steps: tuple[TemplateStep, ...]

    @property
    def step_count(self) -> int:
        """How many agents the pipeline has."""
        return len(self.steps)

    @property
    def stage_count(self) -> int:
        return len({step.stage for step in self.steps})

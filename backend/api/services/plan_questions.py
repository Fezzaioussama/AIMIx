"""The questions the planner may ask before it plans a mission, and the answers it
gets back (§5 S): reading them is kept apart from the prompt that invites them
(``plan_prompts``) and from the call that sends it (``pipelines``)."""

from __future__ import annotations

from dataclasses import dataclass

#: The most questions, and suggested answers per question, a planner reply may hold.
MAX_QUESTIONS = 4
MAX_OPTIONS = 4
#: A question or a suggested answer is cut to this length.
QUESTION_MAX_LENGTH = 300
OPTION_MAX_LENGTH = 120


@dataclass(frozen=True)
class ClarifyingQuestion:
    """A question the planner asks before planning, with answers to pick from."""

    question: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    """What the person answered to one question (or, typed, to several at once)."""

    question: str
    answer: str


@dataclass(frozen=True)
class Clarification:
    """Whether the planner may answer with questions, and the answers it already got.
    It asks once at most: once there are answers, it plans."""

    may_ask: bool = False
    answers: tuple[Answer, ...] = ()

    @property
    def asking(self) -> bool:
        return self.may_ask and not self.answers


def _text(value: object, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _options(raw: object) -> tuple[str, ...]:
    """The distinct, non-blank suggested answers, at most ``MAX_OPTIONS`` of them."""
    items = raw if isinstance(raw, list) else []
    options = dict.fromkeys(_text(item, OPTION_MAX_LENGTH) for item in items)
    return tuple(option for option in options if option)[:MAX_OPTIONS]


def questions_in(reply: object) -> tuple[ClarifyingQuestion, ...]:
    """The questions of a planner reply decoded from JSON (``{"questions": [...]}``):
    those with a non-blank question, at most ``MAX_QUESTIONS``. Anything else in
    the reply, or a reply without questions, gives none."""
    raw = reply.get("questions") if isinstance(reply, dict) else None
    questions = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        text = _text(item.get("question"), QUESTION_MAX_LENGTH)
        if text:
            questions.append(ClarifyingQuestion(text, _options(item.get("options"))))
    return tuple(questions[:MAX_QUESTIONS])

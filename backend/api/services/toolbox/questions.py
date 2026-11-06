"""A step agent's question to the person who started the run (the ``ask_user`` tool).

The tool asks through a ``QuestionGate``: in a recorded run that someone watches, the
run's approval gate (``approvals/gate.py``), which records the question, shows the run
``waiting``, and hands back what the person answered or skipped from the run report.
Nobody answering in time, or the run stopping, counts as no answer. Where nobody
watches the run (a schedule's, a webhook's) or there is no run, the gate is
``NOBODY``: the tool says so at once and the agent decides for itself.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from langchain_core.tools import BaseTool, ToolException

from api.services.toolbox.tools import make_tool

ASK_USER = "ask_user"
QUESTION_MAX_CHARS = 2_000
OPTIONS_MAX = 5
OPTION_MAX_CHARS = 200


class QuestionOutcome(str, Enum):
    """How a question ended."""

    ANSWERED = "answered"
    #: The person chose not to answer.
    SKIPPED = "skipped"
    #: Nobody answered in time, or the run stopped.
    UNANSWERED = "unanswered"
    #: Nobody watches the run (a schedule's, a webhook's), or there is no run.
    UNATTENDED = "unattended"


@dataclass(frozen=True)
class Question:
    """What the agent asks, with the choices it offers, if any (§7 Value Object)."""

    text: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Answer:
    outcome: QuestionOutcome
    #: What the person wrote or chose; "" unless answered.
    text: str = ""


class QuestionGate(Protocol):
    """Port: ask the run's owner one question and wait for the answer."""

    async def ask_question(self, question: Question) -> Answer: ...


class NobodyToAsk:
    """Stands in where nobody can be asked (Null Object)."""

    async def ask_question(self, question: Question) -> Answer:
        return Answer(QuestionOutcome.UNATTENDED)


NOBODY: QuestionGate = NobodyToAsk()


@dataclass(frozen=True)
class RunTools:
    """What a recorded run gives its tools: when it started (``save_artifact`` may
    replace a draft saved since) and the gate its agents ask questions through."""

    drafts_since: datetime | None = None
    questions: QuestionGate = NOBODY


NO_RUN_TOOLS = RunTools()

DECIDE = "Decide yourself, say in your answer what you assumed, and do not ask again."

#: What the agent is told, by how the question ended (Strategy + Registry, §5 O).
REPLIES: dict[QuestionOutcome, Callable[[Answer], str]] = {
    QuestionOutcome.ANSWERED: lambda answer: f"The user answered: {answer.text}",
    QuestionOutcome.SKIPPED: lambda answer: f"The user skipped the question. {DECIDE}",
    QuestionOutcome.UNANSWERED: lambda answer: f"The user did not answer in time. {DECIDE}",
    QuestionOutcome.UNATTENDED: lambda answer: (
        f"Nobody is watching this run, so no one can be asked. {DECIDE}"
    ),
}

DESCRIPTION = (
    "Ask the person who started this run one question and wait for their answer. Use it "
    "only when a decision changes the deliverable and the task does not settle it (which "
    "of several directions, a fact only they know). Give up to 5 short options when there "
    "are natural choices; they can also write their own answer. Ask at most once or twice "
    "per task; otherwise state your assumption and go on. In a scheduled run nobody can "
    "answer: you are told so at once."
)


def checked_question(text: str, options: list[str] | None) -> Question:
    """The question as asked, trimmed and bounded; ``ToolException`` tells the agent
    what to fix."""
    question = text.strip()
    if not question:
        raise ToolException("Ask a question: the text is empty.")
    if len(question) > QUESTION_MAX_CHARS:
        raise ToolException(f"Keep the question under {QUESTION_MAX_CHARS} characters.")
    choices = tuple(dict.fromkeys(option.strip() for option in options or () if option.strip()))
    if len(choices) > OPTIONS_MAX:
        raise ToolException(f"Give at most {OPTIONS_MAX} options.")
    if any(len(choice) > OPTION_MAX_CHARS for choice in choices):
        raise ToolException(f"Keep each option under {OPTION_MAX_CHARS} characters.")
    return Question(question, choices)


def ask_user_tool(gate: QuestionGate) -> BaseTool:
    """The ``ask_user`` tool of one step, asking through ``gate``."""

    async def ask_user(question: str, options: list[str] | None = None) -> str:
        answer = await gate.ask_question(checked_question(question, options))
        return REPLIES[answer.outcome](answer)

    return make_tool(ASK_USER, DESCRIPTION, coroutine=ask_user)


def question_tools(enabled: Collection[str], run: RunTools) -> list[BaseTool]:
    """``ask_user``, when AGENT_BUILTIN_TOOLS names it, asking through the run's gate."""
    return [ask_user_tool(run.questions)] if ASK_USER in enabled else []

"""A step agent asks the person who started the run a question (ask_user): recorded
at the approval gate, answered or skipped from the run report, and answered "nobody
is watching" at once in a run nobody watches."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import ValidationFailed
from api.models import ApprovalKind, ApprovalStatus, RunStatus, RunTrigger, User
from api.repositories import approvals, runs
from api.services.agent_types import RunStepRef
from api.services.approvals.decisions import ApprovalAnswer, answer
from api.services.approvals.gate import ApprovalLimits, RunApprovalGate
from api.services.multiagent.step_agent import run_tools
from api.services.tool_prompts import STEP_AGENT_ASK_GUIDANCE, tool_guidance
from api.services.toolbox.questions import (
    ASK_USER,
    NO_RUN_TOOLS,
    NOBODY,
    Answer,
    Question,
    QuestionOutcome,
    ask_user_tool,
)
from config.settings import pin_settings
from tests.approval_fakes import FAST_LIMITS, file_database, make_owner, make_pipeline, running_run
from tests.conftest import TEST_SETTINGS
from tests.test_endpoints import make_pipeline as make_api_pipeline

QUESTION = Question("Blue or red?", ("Blue", "Red"))
ASKED = {"question": "Blue or red?", "options": ["Blue", "Red"]}
#: A gate whose question expires almost at once.
IMPATIENT = ApprovalLimits(
    timeout_seconds=0.05, poll_seconds=0.01, arguments_max_chars=200, description_max_chars=300
)


class ScriptedGate:
    """Answers every question the same way, and keeps what it was asked."""

    def __init__(self, answer: Answer) -> None:
        self.answer = answer
        self.asked: list[Question] = []

    async def ask_question(self, question: Question) -> Answer:
        self.asked.append(question)
        return self.answer


def ask(gate: Any, question: str, options: list[str] | None = None) -> str:
    """What the tool tells the agent (an error result is text too)."""
    tool = ask_user_tool(gate)
    arguments = {"question": question, "options": options} if options else {"question": question}
    result = asyncio.run(tool.ainvoke(arguments))
    return str(result)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = file_database(tmp_path)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    return make_owner(database)


@pytest.fixture
def run_id(database: Database, owner: User) -> int:
    return running_run(database, owner, make_pipeline(database, owner))


def request_question(session: Session, run_id: int) -> int:
    """A pending question, as a step's gate records it; its id."""
    now = datetime.now(timezone.utc)
    new = approvals.NewApproval(
        run_id=run_id,
        step_order=1,
        tool_name=ASK_USER,
        tool_source="AIMIx",
        tool_description="",
        arguments=dict(ASKED),
        arguments_truncated=False,
        created_at=now,
        expires_at=now.replace(year=now.year + 1),
        kind=ApprovalKind.QUESTION,
    )
    asked = approvals.ask(session, new)
    assert asked is not None
    return asked.id


# --- the tool ------------------------------------------------------------------------


def test_the_tool_tells_the_agent_the_answer_or_why_there_is_none() -> None:
    answered = ScriptedGate(Answer(QuestionOutcome.ANSWERED, "Blue"))

    assert ask(answered, " Blue or red? ", ["Blue", "Red", "Blue"]) == "The user answered: Blue"

    assert answered.asked == [QUESTION]  # trimmed, the repeated option dropped
    assert ask(ScriptedGate(Answer(QuestionOutcome.SKIPPED)), "Blue or red?").startswith(
        "The user skipped the question. Decide yourself"
    )
    assert ask(ScriptedGate(Answer(QuestionOutcome.UNANSWERED)), "Blue or red?").startswith(
        "The user did not answer in time."
    )
    assert ask(NOBODY, "Blue or red?").startswith("Nobody is watching this run")


def test_a_question_must_be_asked_well() -> None:
    gate = ScriptedGate(Answer(QuestionOutcome.ANSWERED, "x"))

    assert ask(gate, "   ") == "Ask a question: the text is empty."
    assert ask(gate, "Pick one", [str(n) for n in range(6)]) == "Give at most 5 options."
    assert ask(gate, "x" * 2_001).startswith("Keep the question under 2000 characters.")
    assert gate.asked == []


def test_a_step_with_the_tool_is_told_when_to_use_it() -> None:
    assert STEP_AGENT_ASK_GUIDANCE in tool_guidance([ASK_USER])
    assert STEP_AGENT_ASK_GUIDANCE not in tool_guidance(["calculator"])


# --- the gate ------------------------------------------------------------------------


async def pending_question(database: Database, run_id: int) -> int:
    """Wait until the step's question is recorded, as a person watching the run would."""
    for _ in range(500):
        with database.session() as session:
            run = runs.load(session, run_id)
        assert run is not None
        if run.pending_approvals:
            asked = run.pending_approvals[0]
            assert (run.status, asked.kind) == (RunStatus.WAITING, ApprovalKind.QUESTION)
            assert (asked.tool_name, asked.arguments) == (ASK_USER, ASKED)
            return asked.id
        await asyncio.sleep(0.01)
    raise AssertionError("the agent never asked")


def reply(database: Database, owner: User, given: ApprovalAnswer) -> None:
    with database.session() as session:
        answer(session, owner, given)


def test_the_gate_hands_the_agent_what_the_person_answered(
    database: Database, owner: User, run_id: int
) -> None:
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS)

    async def ask_and_wait() -> tuple[Answer, int]:
        asked = asyncio.create_task(gate.ask_question(QUESTION))
        approval_id = await pending_question(database, run_id)
        reply(database, owner, ApprovalAnswer(run_id, approval_id, ApprovalStatus.APPROVED, "Blue"))
        return await asked, approval_id

    answered, approval_id = asyncio.run(ask_and_wait())

    assert answered == Answer(QuestionOutcome.ANSWERED, "Blue")
    with database.session() as session:
        run = runs.load(session, run_id)
        assert run is not None and run.status == RunStatus.RUNNING
        assert approvals.answer_of(session, approval_id) == "Blue"


def test_a_skipped_question_and_one_nobody_answers(
    database: Database, owner: User, run_id: int
) -> None:
    patient = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS)

    async def skip() -> Answer:
        asked = asyncio.create_task(patient.ask_question(QUESTION))
        approval_id = await pending_question(database, run_id)
        reply(database, owner, ApprovalAnswer(run_id, approval_id, ApprovalStatus.DECLINED))
        return await asked

    assert asyncio.run(skip()) == Answer(QuestionOutcome.SKIPPED)
    impatient = RunApprovalGate(database, RunStepRef(run_id, 1), IMPATIENT)
    assert asyncio.run(impatient.ask_question(QUESTION)) == Answer(QuestionOutcome.UNANSWERED)


def test_approving_a_question_without_an_answer_is_refused(
    database: Database, owner: User, run_id: int
) -> None:
    with database.session() as session:
        approval_id = request_question(session, run_id)
        with pytest.raises(ValidationFailed) as refused:
            answer(session, owner, ApprovalAnswer(run_id, approval_id, ApprovalStatus.APPROVED))
        assert refused.value.detail == "answer: This question needs an answer, or skip it."
        assert approvals.status_of(session, approval_id) == ApprovalStatus.PENDING


# --- which runs can ask --------------------------------------------------------------


def test_only_a_run_someone_watches_lets_its_agents_ask(
    database: Database, owner: User, run_id: int
) -> None:
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS)
    started = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    with database.session() as session:
        runs.set_status(session, run_id, [RunStatus.RUNNING], {"started_at": started})

    watched = run_tools(database, RunStepRef(run_id, 1), gate)

    assert (watched.drafts_since, watched.questions) == (started, gate)
    with database.session() as session:
        values = {"trigger": RunTrigger.SCHEDULE}
        runs.set_status(session, run_id, [RunStatus.RUNNING], values)
    assert run_tools(database, RunStepRef(run_id, 1), gate).questions is NOBODY
    assert run_tools(database, None, gate) is NO_RUN_TOOLS
    assert run_tools(database, RunStepRef(run_id, 1), None).questions is NOBODY


# --- over HTTP -------------------------------------------------------------------------


@pytest.fixture
def question_tool_enabled() -> Iterator[None]:
    """AGENT_BUILTIN_TOOLS names ask_user (the catalogue reads the process's settings)."""
    tools = [*TEST_SETTINGS.agent_builtin_tools, ASK_USER]
    pin_settings(TEST_SETTINGS.model_copy(update={"agent_builtin_tools": tools}))
    yield
    pin_settings(TEST_SETTINGS)


def test_the_catalogue_lists_the_tool_when_it_is_enabled(
    auth_client: TestClient, question_tool_enabled: None
) -> None:
    listed = {item["name"]: item for item in auth_client.get("/api/agent-tools").json()}

    assert listed[ASK_USER]["source"] == "AIMIx"
    assert listed[ASK_USER]["description"].startswith("Ask the person who started this run")


def test_the_person_answers_a_question_from_the_run(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    run_id = running_run(app.state.database, user, make_api_pipeline(session, user, "Flow"))
    approval_id = request_question(session, run_id)
    asked = auth_client.get(f"/api/runs/{run_id}").json()["pending_approvals"][0]
    assert (asked["kind"], asked["answer"], asked["arguments"]) == ("question", "", ASKED)
    path = f"/api/runs/{run_id}/approvals/{approval_id}"

    blank = auth_client.post(f"{path}/answer", json={"answer": "   "})
    unanswered = auth_client.post(f"{path}/approve")
    answered = auth_client.post(f"{path}/answer", json={"answer": " Blue "})
    again = auth_client.post(f"{path}/answer", json={"answer": "Red"})

    assert (blank.status_code, blank.json()["error"]) == (400, "validation_error")
    assert unanswered.status_code == 400
    assert unanswered.json()["detail"].startswith("answer:")
    assert answered.status_code == 200
    assert (answered.json()["status"], answered.json()["pending_approvals"]) == ("running", [])
    assert again.status_code == 200  # the same answer again changes nothing
    with app.state.database.session() as fresh:
        assert approvals.answer_of(fresh, approval_id) == "Blue"

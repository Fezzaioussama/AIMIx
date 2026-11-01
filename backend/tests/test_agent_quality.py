"""What makes a team's agents work better: one model per new team, inputs that arrive
filled in, every agent told its team, the day and the run, the run's result made of its
deliverables, and a second try after a reply with no text or garbled text."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, cast

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from api.db import Database
from api.exceptions import UpstreamResponseInvalid
from api.models import Pipeline, PipelineStep, User
from api.services import pipelines as service
from api.services.agent_prompts import BRIEF_VALUE_MAX_CHARS, TeamMember, TeamView, team_brief
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.approvals.policy import ApprovalPolicy
from api.services.llm import LLMProfile
from api.services.mcp import MCPConnections
from api.services.multiagent.contracts import RunInputs
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from api.services.multiagent.step_agent import (
    LangGraphStepAgent,
    PipelineAgentGenerator,
    StepAgentDependencies,
)
from api.services.pipeline_inputs import INPUT_DEFAULT_MAX_LENGTH
from api.services.plan_prompts import TEAM_GUIDE, PlanRequest, pipeline_generation_prompt
from tests.conftest import TEST_SETTINGS, FakeProvider

DEFAULT = "deepseek/deepseek-v4-flash"
LIMITS = AgentLimits(timeout_seconds=5.0, recursion_limit=9, mcp_timeout_seconds=1.0)


# --- planning ----------------------------------------------------------------------


def test_new_steps_run_on_the_default_model_unless_the_request_names_another() -> None:
    steps: list[dict[str, Any]] = [
        {"model": "x-ai/grok-4.20"},
        {"model": "minimax/minimax-m2.5"},
        {"model": DEFAULT},
    ]

    service.on_default_model(steps, DEFAULT, "Write the posts with Grok-4.20, please.")

    assert [step["model"] for step in steps] == ["x-ai/grok-4.20", DEFAULT, DEFAULT]


def test_a_planned_input_keeps_the_value_the_request_gave_unless_it_is_too_long() -> None:
    plan = {
        "name": "Notes",
        "steps": [{"prompt": "Summarise {notes}", "model": DEFAULT}],
        "inputs": [
            {"name": "notes", "label": "Notes", "default_value": "  Sara: 1,240 signups  "},
            {
                "name": "data",
                "label": "Data",
                "default_value": "x" * (INPUT_DEFAULT_MAX_LENGTH + 1),
            },
            {"name": "tone", "label": "Tone"},
        ],
    }

    parsed = service.parse_plan(json.dumps(plan), [DEFAULT])

    assert [item["default_value"] for item in parsed["inputs"]] == ["Sara: 1,240 signups", "", ""]


def test_a_new_plan_is_told_how_to_shape_its_team_and_to_keep_one_model() -> None:
    prompt = pipeline_generation_prompt(PlanRequest("Launch posts"), [DEFAULT, "x-ai/grok-4.20"])

    assert TEAM_GUIDE in prompt
    assert f'"model": {DEFAULT} for every step, unless the request asks for another' in prompt
    assert '"default_value": what the description already gives' in prompt
    assert "Put a step in a later stage when it needs another step's result" in TEAM_GUIDE


# --- what an agent is told ----------------------------------------------------------


def test_the_brief_marks_the_agent_and_gives_the_day_and_a_short_view_of_the_inputs() -> None:
    team = TeamView(
        "Launch kit",
        (TeamMember(1, 1, "Researcher", "App facts"), TeamMember(2, 2, "Writer", "Email")),
        (("Notes", "n" * (BRIEF_VALUE_MAX_CHARS + 50)),),
        date(2026, 10, 31),
    )

    brief = team_brief(team, 2)

    assert "- Stage 1, Researcher: App facts\n- Stage 2, Writer: Email (you)" in brief
    assert "Today's date is Saturday 31 October 2026." in brief
    assert "(the rest is in your task when you need it)" in brief
    assert "n" * (BRIEF_VALUE_MAX_CHARS + 1) not in brief


def _step(order: int, role: str, *, is_output: bool = False) -> PipelineStep:
    return PipelineStep(
        order=order,
        stage=order,
        title=f"Step {order}",
        role=role,
        allowed_tools=[],
        is_output=is_output,
        prompt="{input}",
        model=DEFAULT,
    )


class _RecordingAgent:
    def __init__(self) -> None:
        self.contexts: dict[str, str] = {}

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.contexts[task.role] = task.context
        return AgentOutcome(output=f"{task.role} work", tool_calls=[])


def test_each_agent_hears_its_team_and_the_run_result_is_the_deliverables() -> None:
    agent = _RecordingAgent()
    pipeline = snapshot_pipeline(
        Pipeline(name="Launch", steps=[_step(1, "Writer", is_output=True), _step(2, "Checker")])
    )

    result = GraphPipelineRunner(max_parallel_steps=2).run(
        pipeline, agent, RunInputs("A plant-care app launch")
    )

    assert "- Stage 1, Writer: Step 1 (you)" in agent.contexts["Writer"]
    assert "- Stage 2, Checker: Step 2 (you)" in agent.contexts["Checker"]
    assert "- Their request: A plant-care app launch" in agent.contexts["Checker"]
    # The checker's answer is not the result: the writer's deliverable is.
    assert result.final_output == "Writer work"


# --- garbled and empty replies -------------------------------------------------------


def _agent_replying(text: str) -> LangGraphStepAgent:
    model = FakeMessagesListChatModel(responses=[AIMessage(content=text)])
    return LangGraphStepAgent(model, AgentToolset(MCPConnections(), [], ApprovalPolicy()), LIMITS)


@pytest.mark.asyncio
async def test_a_reply_holding_a_model_control_token_is_refused() -> None:
    agent = _agent_replying("happy SSA File AR} ...ovac Direct <|endoftext|>")

    with pytest.raises(UpstreamResponseInvalid, match="garbled text"):
        await agent.reply(AgentTask("Write the email", DEFAULT, "Writer", []))


@pytest.mark.asyncio
async def test_a_clean_reply_passes() -> None:
    outcome = await _agent_replying("Subject: Plantly is here").reply(
        AgentTask("Write the email", DEFAULT, "Writer", [])
    )

    assert outcome.output == "Subject: Plantly is here"


@pytest.mark.asyncio
async def test_a_failed_reply_gets_one_more_try_on_the_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tried: list[str] = []

    async def reply(self: PipelineAgentGenerator, task: AgentTask) -> AgentOutcome:
        tried.append(task.model)
        if len(tried) == 1:
            raise UpstreamResponseInvalid("The pipeline agent returned no text.")
        return AgentOutcome(output="Positioning", tool_calls=[])

    monkeypatch.setattr(PipelineAgentGenerator, "_reply", reply)
    generator = PipelineAgentGenerator(
        cast(Database, None),
        cast(User, None),
        LLMProfile("openrouter", DEFAULT),
        StepAgentDependencies(
            lambda model_id: FakeMessagesListChatModel(responses=[]), TEST_SETTINGS
        ),
    )

    outcome = await generator.execute(AgentTask("Position it", "minimax/minimax-m2.5", "PM", []))

    assert tried == ["minimax/minimax-m2.5", DEFAULT]
    assert outcome.output == "Positioning"


@pytest.mark.asyncio
async def test_a_second_failure_fails_the_step(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reply(self: PipelineAgentGenerator, task: AgentTask) -> AgentOutcome:
        raise UpstreamResponseInvalid("The pipeline agent returned no text.")

    monkeypatch.setattr(PipelineAgentGenerator, "_reply", reply)
    generator = PipelineAgentGenerator(
        cast(Database, None),
        cast(User, None),
        LLMProfile("openrouter", DEFAULT),
        StepAgentDependencies(
            lambda model_id: FakeMessagesListChatModel(responses=[]), TEST_SETTINGS
        ),
    )

    with pytest.raises(UpstreamResponseInvalid):
        await generator.execute(AgentTask("Position it", DEFAULT, "PM", []))


class _PromptRecorder:
    def __init__(self) -> None:
        self.prompts: dict[str, str] = {}

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.prompts[task.role] = task.prompt
        output = "VERDICT: PASS" if task.reviewer else f"{task.role} work"
        return AgentOutcome(output=output, tool_calls=[])


def test_the_final_check_judges_every_deliverable_it_can_send_back() -> None:
    agent = _PromptRecorder()
    check = _step(3, "Checker")
    check.review = {"send_back_to_stage": 1, "max_rounds": 2}
    steps = [_step(1, "Critic", is_output=True), _step(2, "Writer", is_output=True), check]

    GraphPipelineRunner(max_parallel_steps=2).run(
        snapshot_pipeline(Pipeline(name="Email", steps=steps)), agent, RunInputs("the email")
    )

    # The critique was made two stages earlier; the check still sees it, before the rewrite.
    assert agent.prompts["Checker"] == (
        "## Output of step 1\n\nCritic work\n\n## Output of step 2\n\nWriter work"
    )
    assert agent.prompts["Writer"] == "Critic work"


class _ScriptedPlanner(FakeProvider):
    """Answers each planner call with the next of ``replies``."""

    def __init__(self, *replies: str) -> None:
        super().__init__()
        self.replies = list(replies)

    def generate(self, prompt: str, model: str | None = None) -> str:
        self.calls.append((prompt, model))
        return self.replies.pop(0)


PLAN = json.dumps({"name": "Posts", "steps": [{"prompt": "Write {input}", "model": DEFAULT}]})


def test_a_reply_that_is_no_plan_is_asked_for_once_more() -> None:
    planner = _ScriptedPlanner('{"name": "Posts", "steps": [ {"prompt" "x"} ]}', PLAN)

    plan = service.generate(
        planner, LLMProfile("openrouter", DEFAULT), service.PlanRequest("posts")
    )

    assert len(planner.calls) == 2
    assert plan.pipeline is not None and plan.pipeline["name"] == "Posts"


def test_a_second_reply_that_is_no_plan_fails_the_request() -> None:
    planner = _ScriptedPlanner("not json", "still not json")

    with pytest.raises(UpstreamResponseInvalid):
        service.generate(planner, LLMProfile("openrouter", DEFAULT), service.PlanRequest("posts"))
    assert len(planner.calls) == 2


@pytest.mark.asyncio
async def test_when_the_default_model_itself_fails_it_tries_again_without_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tried: list[tuple[str, list[str] | None]] = []

    async def reply(self: PipelineAgentGenerator, task: AgentTask) -> AgentOutcome:
        tried.append((task.model, task.allowed_tools))
        if len(tried) == 1:
            raise UpstreamResponseInvalid("The pipeline agent returned no text.")
        return AgentOutcome(output="Trends", tool_calls=[])

    monkeypatch.setattr(PipelineAgentGenerator, "_reply", reply)
    generator = PipelineAgentGenerator(
        cast(Database, None),
        cast(User, None),
        LLMProfile("openrouter", DEFAULT),
        StepAgentDependencies(
            lambda model_id: FakeMessagesListChatModel(responses=[]), TEST_SETTINGS
        ),
    )

    await generator.execute(AgentTask("Read the data", DEFAULT, "Analyst", ["read_csv"]))

    assert tried == [(DEFAULT, ["read_csv"]), (DEFAULT, [])]

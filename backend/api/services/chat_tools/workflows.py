"""Chat tools that build and change workflows with the Missions planner (AGENTS.md §3):
a team made by chatting gets the same team guide, the person's own tools and models,
and the final check as one made in Missions, and is saved like one saved there."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool

from api.exceptions import DomainError
from api.models import Pipeline
from api.repositories import pipelines as repository
from api.schemas.pipelines import PipelineIn, PipelineOut, PipelinePatch
from api.schemas.planning import PipelineDraftIn
from api.services import pipelines as pipeline_service
from api.services import run_feedback, user_memory
from api.services.agent_types import ToolDescriptor
from api.services.chat_tools.common import refused, save_new, save_patch, session_user
from api.services.chat_tools.scope import ChatScope
from api.services.pipeline_revision import RevisionRequest, revise

#: How a team summary names the tools of an agent that may use every tool the person has.
ALL_TOOLS = "all"


def team_of(pipeline: Pipeline) -> dict[str, Any]:
    """A saved workflow as the chat describes it: its name, run inputs and agents."""
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "inputs": [field["name"] for field in pipeline.inputs],
        "agents": [
            {
                "stage": step.stage,
                "title": step.title,
                "role": step.role,
                "model": step.model,
                "tools": ALL_TOOLS if step.allowed_tools is None else step.allowed_tools,
            }
            for step in pipeline.steps
        ],
    }


def draft_of(pipeline: Pipeline) -> dict[str, Any]:
    """A saved pipeline as the revision planner reads it: the draft Missions sends."""
    saved = PipelineOut.model_validate(pipeline).model_dump()
    return PipelineDraftIn.model_validate(saved).model_dump()


def workflow_tools(scope: ChatScope) -> list[BaseTool]:
    """Bind the planner's design and change tools, and the tool list, to one person."""

    def catalog() -> list[ToolDescriptor]:
        return scope.catalog(scope.database, scope.user).available_sync()

    def instructions() -> str:
        """What the person told AIMIx to keep in mind (Settings → Memory)."""
        with scope.database.session() as session:
            return user_memory.instructions_for(session, scope.user)

    def lessons() -> tuple[run_feedback.Lesson, ...]:
        """What the person said of their latest runs, for a new team."""
        with scope.database.session() as session:
            return run_feedback.lessons_for(session, scope.user)

    @tool
    def list_tools() -> list[dict[str, str]]:
        """List the tools the agents of a workflow can use (web search, files,
        pictures, connected apps), with what each does and where it comes from."""
        return [asdict(item) for item in catalog()]

    @tool
    def design_workflow(description: str) -> dict[str, Any]:
        """Plan a new workflow from the person's request and save it. The AIMIx
        planner picks the agents, their stages, models and tools, and ends the team
        with a final check. Put every detail the person gave in description: topic,
        audience, format, length, language, sources. Returns the saved team."""
        try:
            request = pipeline_service.PlanRequest(
                description, instructions=instructions(), lessons=lessons()
            )
            planner = scope.planner(scope.profile)
            plan = pipeline_service.generate(planner, scope.profile, request, catalog())
            body = PipelineIn.model_validate(plan.pipeline)
            with scope.database.session() as session:
                return team_of(save_new(session, scope.user, body))
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    @tool
    def change_workflow(pipeline_id: int, change: str) -> dict[str, Any]:
        """Change one of your saved workflows as the person describes it, for example
        "add an agent that checks the facts" or "make the summary shorter", and save
        it. Returns the team and what changed."""
        try:
            with scope.database.session() as session:
                owner = session_user(session, scope.user)
                draft = draft_of(repository.get_owned(session, owner, pipeline_id))
            planner = scope.planner(scope.profile)
            request = RevisionRequest(draft, change, instructions=instructions())
            revision = revise(planner, scope.profile, request, catalog())
            body = PipelinePatch.model_validate(revision.pipeline)
            with scope.database.session() as session:
                team = team_of(save_patch(session, scope.user, pipeline_id, body))
            return {**team, "changes": [asdict(item) for item in revision.changes]}
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    return [list_tools, design_workflow, change_workflow]

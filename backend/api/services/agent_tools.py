"""Native AIMIx functions exposed to chat and pipeline agents as LangChain tools."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool, ToolException

from api.db import Database
from api.exceptions import DomainError, ProviderNotConfigured, RunStillRunning, Throttled
from api.models import Pipeline, User
from api.repositories import pipelines as repository
from api.repositories import schedules as schedule_repository
from api.schemas.pipelines import PipelineIn, PipelinePatch
from api.schemas.schedules import ScheduleIn, SchedulePatch
from api.security import secret_box_for
from api.services import llm_settings
from api.services.catalog import known_model_ids
from api.services.chat_tools.common import refused, save_new, save_patch, session_user
from api.services.files.storage import user_workspace_dir
from api.services.llm import get_image_generator, get_object_finder
from api.services.multiagent.contracts import RunResult
from api.services.rate_limits import RateLimitRequest, enforce
from api.services.run_recorder import utcnow
from api.services.runs import RunStart
from api.services.schedules import requests as schedule_requests
from api.services.schedules import service as schedule_service
from api.services.schedules.service import ScheduleAccess, ScheduleView
from api.services.toolbox.config import MetaTools, SandboxQuota, toolbox_config
from api.services.toolbox.registry import toolbox_tools
from config.settings import Settings, get_settings
from llm.providers import meta

logger = logging.getLogger(__name__)

#: The rate-limit bucket run_python calls count against, one per account.
SANDBOX_ACTION = "tool:run_python"
SANDBOX_WINDOW_SECONDS = 3600

#: Runs one of the signed-in user's saved pipelines to its end, recorded in
#: their run history (``services/runs.launcher``).
PipelineLauncher = Callable[[int, RunStart], RunResult]


def _pipeline_details(pipeline: Pipeline) -> dict[str, Any]:
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "inputs": pipeline.inputs,
        "steps": [
            {
                "order": step.order,
                "stage": step.stage,
                "title": step.title,
                "prompt": step.prompt,
                "model": step.model,
                "role": step.role,
                "allowed_tools": step.allowed_tools,
                "is_output": step.is_output,
                "expected_output": step.expected_output,
                "condition": step.condition,
                "review": step.review,
            }
            for step in pipeline.steps
        ],
    }


def read_only_tools(database: Database, user: User) -> list[BaseTool]:
    """Bind native inspection functions to one authenticated user."""

    @tool
    def list_pipelines() -> list[dict[str, int | str]]:
        """List your saved AIMIx pipelines with their ids, names, and step counts."""
        with database.session() as session:
            return [
                {"id": row.id, "name": row.name, "step_count": len(row.steps)}
                for row in repository.for_user(session, user)
            ]

    @tool
    def inspect_pipeline(pipeline_id: int) -> dict[str, Any]:
        """Inspect one of your saved AIMIx pipelines: its named inputs and its steps'
        prompts, models and expected outputs."""
        with database.session() as session:
            return _pipeline_details(repository.get_owned(session, user, pipeline_id))

    return [list_pipelines, inspect_pipeline]


def sandbox_quota(database: Database, user: User, settings: Settings) -> SandboxQuota:
    """Spends one of ``user``'s SANDBOX_MAX_CALLS_PER_HOUR run_python calls: each
    one spends the server's E2B_API_KEY, so no account may use it unboundedly."""
    limit = settings.sandbox_max_calls_per_hour
    request = RateLimitRequest(
        f"user:{user.id}",
        SANDBOX_ACTION,
        limit,
        SANDBOX_WINDOW_SECONDS,
        f"run_python is limited to {limit} calls an hour per account. Try again later.",
    )

    def spend() -> None:
        with database.session() as session:
            try:
                enforce(session, settings.secret_key, request)
            except Throttled as cause:
                logger.warning("sandbox.quota_exhausted user_id=%s", user.id)
                raise ToolException(str(cause)) from cause

    return spend


def meta_tools(database: Database, user: User, settings: Settings) -> MetaTools | None:
    """Muse Image and SAM 3.1 on the user's Meta key, or the server's when
    ALLOW_SERVER_LLM_KEY shares it; None without one, so their tools are not offered."""
    with database.session() as session:
        try:
            profile = llm_settings.provider_profile(
                session, user, secret_box_for(settings), meta.NAME
            )
            return MetaTools(get_image_generator(profile), get_object_finder(profile))
        except ProviderNotConfigured:
            return None


def native_tools(
    database: Database, user: User, settings: Settings, drafts_since: datetime | None = None
) -> list[BaseTool]:
    """Every in-process tool an agent may use: pipeline inspection plus the built-in
    toolbox; a run's agents may replace the files saved since ``drafts_since``."""
    workspace = user_workspace_dir(settings.workspace_dir, user.id)
    quota = sandbox_quota(database, user, settings)
    config = toolbox_config(settings, workspace, quota, meta_tools(database, user, settings))
    return [
        *read_only_tools(database, user),
        *toolbox_tools(replace(config, drafts_since=drafts_since)),
    ]


def _pipeline_summary(pipeline: Pipeline) -> dict[str, Any]:
    """The short pipeline shape a chat tool returns to the model."""
    return {"id": pipeline.id, "name": pipeline.name, "step_count": len(pipeline.steps)}


def _schedule_summary(view: ScheduleView) -> dict[str, Any]:
    """The short schedule shape a chat tool returns to the model."""
    return {
        "id": view.id,
        "pipeline_id": view.pipeline_id,
        "pipeline_name": view.pipeline_name,
        "frequency": view.frequency.value,
        "time": view.at.strftime("%H:%M"),
        "timezone": view.timezone,
        "weekday": view.weekday,
        "day_of_month": view.day_of_month,
        "enabled": view.enabled,
        "next_run_at": None if view.next_run_at is None else view.next_run_at.isoformat(),
    }


def _numbered(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Steps numbered by position unless they already say where they go."""
    return [{"order": index, **step} for index, step in enumerate(steps, start=1)]


def built_in_tools(
    database: Database, user: User, launch: PipelineLauncher, schedules: ScheduleAccess
) -> list[BaseTool]:
    """Bind the chat's pipeline and schedule functions to the authenticated user.

    Destructive actions (deleting a pipeline or a schedule) stay on their screens:
    a chat message has nowhere to ask for the confirmation those need.
    """
    native = native_tools(database, user, get_settings())

    @tool
    def run_pipeline(
        pipeline_id: int, input_text: str = "", inputs: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Run one of your saved AIMIx pipelines and return its step results. Pass
        input_text, or, when the pipeline declares named inputs (see
        inspect_pipeline), a value for each of them in inputs. A long run goes on
        in the background: follow it with get_run."""
        try:
            return asdict(launch(pipeline_id, RunStart(input_text, inputs or {})))
        except RunStillRunning as running:
            return {"id": running.run_id, "status": "running"}
        except DomainError as cause:
            raise refused(cause) from cause

    @tool
    def list_models() -> list[str]:
        """List the model ids a pipeline step may name."""
        return known_model_ids()

    @tool
    def create_pipeline(
        name: str, steps: list[dict[str, Any]], inputs: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """Create and save a new AIMIx pipeline. Each step needs a prompt and a
        model; its order defaults to its position, and it may also set stage,
        title, role, allowed_tools, is_output and expected_output. Each input is
        {name, label, description}."""
        try:
            body = PipelineIn.model_validate(
                {"name": name, "steps": _numbered(steps), "inputs": inputs or []}
            )
            with database.session() as session:
                return _pipeline_summary(save_new(session, user, body))
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    @tool
    def update_pipeline(
        pipeline_id: int,
        name: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        inputs: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Change one of your saved pipelines: rename it, replace its steps, and/or
        redeclare its inputs. Send at least one of name, steps or inputs. A step
        keeps an explicit order, else its position is used."""
        sent = {"name": name, "steps": steps, "inputs": inputs}
        data = {key: value for key, value in sent.items() if value is not None}
        if not data:
            raise ToolException("Send at least one of name, steps or inputs.")
        try:
            if steps is not None:
                data["steps"] = _numbered(steps)
            body = PipelinePatch.model_validate(data)
            with database.session() as session:
                return _pipeline_summary(save_patch(session, user, pipeline_id, body))
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    @tool
    def list_schedules(pipeline_id: int | None = None) -> list[dict[str, Any]]:
        """List your scheduled runs, optionally only those of one pipeline
        (see list_pipelines), with when each runs and whether it is on."""
        with database.session() as session:
            access = replace(
                schedules, session=session, user=session_user(session, user), now=utcnow()
            )
            views = schedule_service.list_views(access, pipeline_id)
            return [_schedule_summary(view) for view in views]

    @tool
    def create_schedule(
        pipeline_id: int,
        frequency: str,
        time: str,
        timezone: str,
        weekday: int | None = None,
        day_of_month: int | None = None,
        input_text: str = "",
        inputs: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Schedule one of your saved pipelines. frequency is hourly, daily,
        weekdays, weekly or monthly; time is "HH:MM" in an IANA timezone
        ("Europe/Paris"). weekly takes a weekday (0 is Monday), monthly a
        day_of_month. Give what each run is passed as input_text or inputs."""
        try:
            body = ScheduleIn.model_validate(
                {
                    "pipeline_id": pipeline_id,
                    "frequency": frequency,
                    "time": time,
                    "timezone": timezone,
                    "weekday": weekday,
                    "day_of_month": day_of_month,
                    "input": input_text,
                    "inputs": inputs or {},
                    "enabled": enabled,
                }
            )
            with database.session() as session:
                access = replace(
                    schedules, session=session, user=session_user(session, user), now=utcnow()
                )
                return _schedule_summary(
                    schedule_service.create(access, schedule_requests.draft_of(body))
                )
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    @tool
    def update_schedule(
        schedule_id: int,
        frequency: str | None = None,
        time: str | None = None,
        timezone: str | None = None,
        weekday: int | None = None,
        day_of_month: int | None = None,
        input_text: str | None = None,
        inputs: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Change one of your schedules: its timing, what each run is passed,
        or whether it is on (enabled=false pauses it). Omitted fields keep
        their value."""
        sent: dict[str, Any] = {
            "frequency": frequency,
            "time": time,
            "timezone": timezone,
            "weekday": weekday,
            "day_of_month": day_of_month,
            "input": input_text,
            "inputs": inputs,
            "enabled": enabled,
        }
        data = {key: value for key, value in sent.items() if value is not None}
        if not data:
            raise ToolException("Send at least one field to change.")
        try:
            with database.session() as session:
                owner = session_user(session, user)
                # input and inputs replace each other; keep the untouched one.
                if (input_text is None) != (inputs is None):
                    current = schedule_repository.get_owned(session, owner, schedule_id)
                    if input_text is None:
                        input_text = current.input_text
                    if inputs is None:
                        inputs = dict(current.input_values)
                body = SchedulePatch.model_validate(
                    {
                        **{key: value for key, value in sent.items() if value is not None},
                        "input": input_text,
                        "inputs": inputs,
                    }
                )
                access = replace(schedules, session=session, user=owner, now=utcnow())
                return _schedule_summary(
                    schedule_service.update(access, schedule_id, schedule_requests.edit_of(body))
                )
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    return [
        *native,
        list_models,
        run_pipeline,
        create_pipeline,
        update_pipeline,
        list_schedules,
        create_schedule,
        update_schedule,
    ]

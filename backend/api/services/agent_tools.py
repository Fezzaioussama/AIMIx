"""Native AIMIx functions exposed to chat and pipeline agents as LangChain tools."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool, ToolException

from api.db import Database
from api.exceptions import ProviderNotConfigured, Throttled
from api.models import Pipeline, User
from api.repositories import pipelines as repository
from api.security import secret_box_for
from api.services import llm_settings
from api.services.files.storage import user_workspace_dir
from api.services.llm import get_image_generator
from api.services.multiagent.contracts import RunResult
from api.services.rate_limits import RateLimitRequest, enforce
from api.services.runs import RunStart
from api.services.toolbox.config import SandboxQuota, toolbox_config
from api.services.toolbox.registry import toolbox_tools
from config.settings import Settings, get_settings
from llm.images import PROVIDER as IMAGE_PROVIDER
from llm.images import ImageGenerator

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


def image_generator(database: Database, user: User, settings: Settings) -> ImageGenerator | None:
    """Muse Image on the user's Meta key, or the server's when ALLOW_SERVER_LLM_KEY
    shares it; None without one, so generate_image is not offered."""
    with database.session() as session:
        try:
            profile = llm_settings.provider_profile(
                session, user, secret_box_for(settings), IMAGE_PROVIDER
            )
            return get_image_generator(profile)
        except ProviderNotConfigured:
            return None


def native_tools(database: Database, user: User, settings: Settings) -> list[BaseTool]:
    """Every in-process tool an agent may use: pipeline inspection plus the
    built-in toolbox (web search, page fetch, calculator, clock, pictures)."""
    workspace = user_workspace_dir(settings.workspace_dir, user.id)
    quota = sandbox_quota(database, user, settings)
    images = image_generator(database, user, settings)
    return [
        *read_only_tools(database, user),
        *toolbox_tools(toolbox_config(settings, workspace, quota, images)),
    ]


def built_in_tools(database: Database, user: User, launch: PipelineLauncher) -> list[BaseTool]:
    """Bind pipeline functions to the authenticated user for one agent run."""
    native = native_tools(database, user, get_settings())

    @tool
    def run_pipeline(
        pipeline_id: int, input_text: str = "", inputs: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Run one of your saved AIMIx pipelines and return its step results. Pass
        input_text, or, when the pipeline declares named inputs (see
        inspect_pipeline), a value for each of them in inputs."""
        return asdict(launch(pipeline_id, RunStart(input_text, inputs or {})))

    return [*native, run_pipeline]

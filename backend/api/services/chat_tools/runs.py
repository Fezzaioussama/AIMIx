"""Chat tools that follow and steer runs as the Runs screen does (AGENTS.md §3): the same
ownership rules and run service, and a result cut to what a chat message can hold.
Approving a tool call stays on the run's screen: a person must click it, not a model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool

from api.exceptions import DomainError
from api.models import Run
from api.repositories import runs as repository
from api.schemas.runs import RunListQuery
from api.services.chat_tools.common import refused, session_user
from api.services.chat_tools.scope import ChatScope
from config.settings import get_settings


def _when(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def run_summary(run: Run) -> dict[str, Any]:
    """A run as a list shows it: which workflow, where it is, who started it, when."""
    return {
        "id": run.id,
        "workflow": run.pipeline_name,
        "status": run.status.value,
        "started_by": run.trigger.value,
        "created_at": _when(run.created_at),
        "finished_at": _when(run.finished_at),
        "error": run.error_detail or None,
    }


def run_details(run: Run, result_max_chars: int) -> dict[str, Any]:
    """A run as the chat tells it: each agent's state, what waits for the person's OK
    (approved on the run's screen), and its result, cut at ``result_max_chars``."""
    result = run.final_output
    return {
        **run_summary(run),
        "agents": [{"title": step.title, "status": step.status.value} for step in run.steps],
        "waiting_for_your_ok": [approval.tool_name for approval in run.pending_approvals],
        "result": result[:result_max_chars],
        "result_cut": len(result) > result_max_chars,
    }


def run_tools(scope: ChatScope) -> list[BaseTool]:
    """Bind the run tools to the signed-in person."""

    def details(run_id: int) -> dict[str, Any]:
        with scope.database.session() as session:
            run = repository.get_owned(session, session_user(session, scope.user), run_id)
            return run_details(run, get_settings().chat_run_result_max_chars)

    @tool
    def list_runs(
        pipeline_id: int | None = None, status: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """List your latest runs, newest first: all of them, those of one workflow,
        or those with one status (queued, running, waiting, succeeded, failed,
        cancelled, interrupted)."""
        try:
            query = RunListQuery.model_validate(
                {"limit": limit, "pipeline_id": pipeline_id, "status": status}
            )
        except ValueError as cause:
            raise refused(cause) from cause
        with scope.database.session() as session:
            page = repository.page_for_user(
                session,
                session_user(session, scope.user),
                repository.RunQuery(query.limit, 0, query.pipeline_id, query.status),
            )
            return [run_summary(run) for run in page.items]

    @tool
    def get_run(run_id: int) -> dict[str, Any]:
        """See one run: its status, each agent's progress, the tool calls waiting for
        your OK, and its result."""
        try:
            return details(run_id)
        except DomainError as cause:
            raise refused(cause) from cause

    @tool
    def stop_run(run_id: int) -> dict[str, Any]:
        """Stop a queued, running or waiting run; it can be resumed later. A run
        that already ended stays as it is."""
        try:
            scope.runs.cancel(scope.user, run_id)
            return details(run_id)
        except DomainError as cause:
            raise refused(cause) from cause

    @tool
    def resume_run(run_id: int) -> dict[str, Any]:
        """Continue a failed, stopped or interrupted run from its first unfinished
        stage, with your current model and key. Any other run stays as it is."""
        try:
            scope.runs.resume(scope.user, run_id, scope.agents())
            return details(run_id)
        except DomainError as cause:
            raise refused(cause) from cause

    return [list_runs, get_run, stop_run, resume_run]

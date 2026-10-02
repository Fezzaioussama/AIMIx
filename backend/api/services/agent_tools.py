"""Native AIMIx functions exposed to the chat agent as LangChain tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool

from api.db import Database
from api.exceptions import ValidationFailed
from api.models import Pipeline, User
from api.repositories import pipelines as repository
from api.services import pipelines as pipeline_service
from llm.base import LLMProvider


def _pipeline_details(pipeline: Pipeline) -> dict[str, Any]:
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "steps": [
            {
                "order": step.order,
                "stage": step.stage,
                "title": step.title,
                "prompt": step.prompt,
                "model": step.model,
                "is_output": step.is_output,
            }
            for step in pipeline.steps
        ],
    }


def built_in_tools(
    database: Database, user: User, provider_factory: Callable[[], LLMProvider]
) -> list[BaseTool]:
    """Bind pipeline functions to the authenticated user for one agent run."""

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
        """Inspect one of your saved AIMIx pipelines, including its step prompts and models."""
        with database.session() as session:
            return _pipeline_details(repository.get_owned(session, user, pipeline_id))

    @tool
    def run_pipeline(pipeline_id: int, input_text: str) -> dict[str, Any]:
        """Run one of your saved AIMIx pipelines on input_text and return its step results."""
        if not input_text.strip():
            raise ValidationFailed("Pipeline input must not be blank.")
        with database.session() as session:
            pipeline = repository.get_owned(session, user, pipeline_id)
            pipeline_service.ensure_runnable(pipeline)
        return asdict(pipeline_service.run(pipeline, provider_factory(), input_text))

    return [list_pipelines, inspect_pipeline, run_pipeline]

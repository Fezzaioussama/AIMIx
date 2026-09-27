"""Data access for pipelines (AGENTS.md §7 Repository).

Services and serializers go through these helpers instead of writing queryset
logic inline, so ownership filtering lives in exactly one place.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet

from api.exceptions import NotFound
from api.models import Pipeline, PipelineStep


def for_user(user: User) -> QuerySet[Pipeline]:
    return Pipeline.objects.filter(user=user).prefetch_related("steps")


def get_owned(user: User, pipeline_id: int) -> Pipeline:
    """Fetch a pipeline the user owns, or raise NotFound.

    Ownership is part of the lookup rather than a separate check, so a pipeline
    belonging to someone else is indistinguishable from one that is absent.
    """
    pipeline = for_user(user).filter(pk=pipeline_id).first()
    if pipeline is None:
        raise NotFound(f"Pipeline {pipeline_id} was not found.")
    return pipeline


@transaction.atomic
def create_with_steps(*, user: User, name: str, steps: Iterable[dict[str, Any]]) -> Pipeline:
    pipeline = Pipeline.objects.create(user=user, name=name)
    _write_steps(pipeline, steps)
    return pipeline


@transaction.atomic
def replace_steps(
    pipeline: Pipeline, name: str | None, steps: Iterable[dict[str, Any]] | None
) -> Pipeline:
    if name is not None:
        pipeline.name = name
        pipeline.save(update_fields=["name"])
    if steps is not None:
        pipeline.steps.all().delete()
        _write_steps(pipeline, steps)
    return pipeline


def _write_steps(pipeline: Pipeline, steps: Iterable[dict[str, Any]]) -> None:
    PipelineStep.objects.bulk_create(PipelineStep(pipeline=pipeline, **step) for step in steps)

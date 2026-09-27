"""Data migrations that rewrite stored values."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.test import override_settings

from api.models import Pipeline, PipelineStep

fix_ids = importlib.import_module("api.migrations.0005_fix_openrouter_model_ids")
add_stage = importlib.import_module("api.migrations.0006_pipelinestep_stage")

pytestmark = pytest.mark.django_db

OLD_QWEN = "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"


def make_step(user: User, model: str) -> PipelineStep:
    pipeline = Pipeline.objects.create(user=user, name="Stale")
    return PipelineStep.objects.create(
        pipeline=pipeline, order=1, stage=1, prompt="{input}", model=model
    )


@override_settings(LLM_PROVIDER="openrouter")
def test_openrouter_steps_move_to_valid_ids_and_back(user: User) -> None:
    step = make_step(user, OLD_QWEN)

    fix_ids.forwards(apps, None)
    step.refresh_from_db()
    assert step.model == "qwen/qwen3-coder"

    fix_ids.backwards(apps, None)
    step.refresh_from_db()
    assert step.model == OLD_QWEN


@override_settings(LLM_PROVIDER="togetherai")
def test_togetherai_steps_are_left_alone(user: User) -> None:
    # The old id is still valid on TogetherAI.
    step = make_step(user, OLD_QWEN)

    fix_ids.forwards(apps, None)
    step.refresh_from_db()
    assert step.model == OLD_QWEN


def test_existing_steps_keep_running_sequentially(user: User) -> None:
    step = make_step(user, OLD_QWEN)
    PipelineStep.objects.filter(pk=step.pk).update(order=4, stage=1)

    add_stage.stage_from_order(apps, None)
    step.refresh_from_db()
    assert step.stage == 4

"""Rewrite pipeline steps saved with OpenRouter model ids that OpenRouter rejects.

The OpenRouter catalogue used TogetherAI-style ids (and a retired Grok id), so
those steps failed at run time with ``provider_unavailable``. The mapping is
frozen here on purpose: a migration must not import the live catalogue.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import migrations

from llm.registry import canonical_name

OPENROUTER_ID_FIXES = {
    "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8": "qwen/qwen3-coder",
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": "meta-llama/llama-4-maverick",
    "x-ai/grok-4.1-fast": "x-ai/grok-4.20",
}


def _swap(apps: Any, mapping: dict[str, str]) -> None:
    # The old Qwen/Llama ids are still valid on TogetherAI, so only rewrite
    # steps when OpenRouter is the configured provider.
    if canonical_name(settings.LLM_PROVIDER) != "openrouter":
        return
    step_model = apps.get_model("api", "PipelineStep")
    for old, new in mapping.items():
        step_model.objects.filter(model=old).update(model=new)


def forwards(apps: Any, schema_editor: Any) -> None:
    _swap(apps, OPENROUTER_ID_FIXES)


def backwards(apps: Any, schema_editor: Any) -> None:
    _swap(apps, {new: old for old, new in OPENROUTER_ID_FIXES.items()})


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0004_alter_pipeline_options_alter_pipeline_user_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]

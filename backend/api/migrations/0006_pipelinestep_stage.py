"""Add ``PipelineStep.stage``. Existing steps get ``stage = order`` so every saved
pipeline keeps running as the sequential chain it was built as."""

from __future__ import annotations

from typing import Any

from django.db import migrations, models
from django.db.models import F


def stage_from_order(apps: Any, schema_editor: Any) -> None:
    apps.get_model("api", "PipelineStep").objects.update(stage=F("order"))


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0005_fix_openrouter_model_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinestep",
            name="stage",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(stage_from_order, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pipelinestep",
            name="stage",
            field=models.PositiveIntegerField(
                help_text="Execution stage. Steps in the same stage run in parallel."
            ),
        ),
        migrations.AlterModelOptions(
            name="pipelinestep",
            options={"ordering": ["stage", "order"]},
        ),
    ]

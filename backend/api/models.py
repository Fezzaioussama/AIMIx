"""Persistence and the invariants that belong to each entity (AGENTS.md §2)."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models

STEP_TITLE_MAX_LENGTH = 100


class Pipeline(models.Model):
    """A named, ordered chain of LLM steps owned by one user."""

    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pipelines")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class PipelineStep(models.Model):
    """One step of a pipeline. ``prompt`` may contain the {input} placeholder,
    which the runner substitutes with the previous stage's output.

    Steps sharing a ``stage`` run in parallel on the same input; stages run in
    ascending order, so ``stage == order`` for every step is a plain chain.

    ``is_output`` marks a step whose result is a deliverable of the pipeline
    rather than intermediate work. When no step is marked, the last stage's
    steps are the outputs. Output steps still feed any later stage.
    """

    pipeline = models.ForeignKey(Pipeline, related_name="steps", on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    prompt = models.TextField(
        help_text="Prompt template for this step. Use {input} as the placeholder."
    )
    model = models.CharField(
        max_length=200,
        help_text="Model id, validated against the provider catalogue on write.",
    )
    stage = models.PositiveIntegerField(
        help_text="Execution stage. Steps in the same stage run in parallel."
    )
    title = models.CharField(
        max_length=STEP_TITLE_MAX_LENGTH,
        blank=True,
        default="",
        help_text="Short name shown in the UI.",
    )
    is_output = models.BooleanField(
        default=False, help_text="Show this step's result as a pipeline output."
    )

    class Meta:
        ordering = ["stage", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline", "order"], name="unique_step_order_per_pipeline"
            )
        ]

    def __str__(self) -> str:
        return f"{self.pipeline.name} — step {self.order} ({self.model})"

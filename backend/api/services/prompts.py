"""Prompt templates. Kept apart from transport and persistence so a service that
builds a prompt does not also perform the call (AGENTS.md §5 S)."""

from __future__ import annotations

PIPELINE_GENERATION_TEMPLATE = """You are an AI pipeline architect. Given a user's \
description of a workflow, generate a structured multi-step pipeline.

Each step should have:
1. A clear, specific prompt template that uses {{input}} as a placeholder for the \
previous step's output
2. A recommended model from this list: {models}

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{{
  "name": "Pipeline Name",
  "steps": [
    {{"order": 1, "prompt": "Your prompt with {{input}}", "model": "model-name"}},
    {{"order": 2, "prompt": "Next prompt with {{input}}", "model": "model-name"}}
  ]
}}

User's workflow description:
"""


def pipeline_generation_prompt(description: str, available_models: list[str]) -> str:
    """Render the planner prompt for a workflow description."""
    header = PIPELINE_GENERATION_TEMPLATE.format(models=", ".join(available_models))
    return f"{header}{description}"


def step_prompt(template: str, current_input: str) -> str:
    """Substitute the running value into a step template.

    ``{input}`` is replaced where present; otherwise the value is appended, so a
    template without the placeholder still receives its input.
    """
    if "{input}" in template:
        return template.replace("{input}", current_input)
    return f"{template}\n\nInput: {current_input}"

"""A pipeline's named run inputs: how they may be named, and checking a run's
values against them before any agent starts (AGENTS.md §6, fail fast)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from api.exceptions import ValidationFailed
from api.models import (
    PIPELINE_INPUT_NAME_MAX_LENGTH,
    PIPELINE_INPUT_NAME_PATTERN,
    RESERVED_INPUT_NAME,
)
from api.services.multiagent.contracts import InputField, RunInputs
from api.services.prompts import merge_input_values

_INPUT_NAME = re.compile(PIPELINE_INPUT_NAME_PATTERN)


def input_name_error(name: str) -> str | None:
    """Why ``name`` cannot name a pipeline input, or None when it can."""
    if not _INPUT_NAME.fullmatch(name):
        return "An input name starts with a lowercase letter and uses only a-z, 0-9 and _."
    if len(name) > PIPELINE_INPUT_NAME_MAX_LENGTH:
        return f"An input name has at most {PIPELINE_INPUT_NAME_MAX_LENGTH} characters."
    if name == RESERVED_INPUT_NAME:
        return f"'{RESERVED_INPUT_NAME}' is reserved: {{input}} is each stage's input."
    return None


def bind_run_inputs(
    fields: Sequence[InputField], text: str, values: Mapping[str, str]
) -> RunInputs:
    """Check a run request against the inputs its pipeline declares.

    A pipeline without named inputs runs on ``text``. One that declares them
    needs a non-blank value for each and nothing else; its first stage receives
    them all, labelled, and every step can insert any of them by name.
    """
    if not fields:
        return _bind_text(text, values)
    return _bind_values(fields, text, values)


def _bind_text(text: str, values: Mapping[str, str]) -> RunInputs:
    if values:
        raise ValidationFailed("This pipeline has no named inputs; send its input as text.")
    if not text.strip():
        raise ValidationFailed("Pipeline input must not be blank.")
    return RunInputs(text.strip())


def _bind_values(fields: Sequence[InputField], text: str, values: Mapping[str, str]) -> RunInputs:
    names = ", ".join(field.name for field in fields)
    if text.strip():
        raise ValidationFailed(f"This pipeline takes named inputs instead of text: {names}.")
    unknown = sorted(set(values) - {field.name for field in fields})
    if unknown:
        raise ValidationFailed(f"Unknown input '{unknown[0]}'. This pipeline takes: {names}.")
    bound = {field.name: values.get(field.name, "").strip() for field in fields}
    missing = [field.display_label for field in fields if not bound[field.name]]
    if missing:
        raise ValidationFailed(f"Fill in {', '.join(missing)} to run this pipeline.")
    first_stage_input = merge_input_values(
        [(field.display_label, bound[field.name]) for field in fields]
    )
    return RunInputs(first_stage_input, bound)

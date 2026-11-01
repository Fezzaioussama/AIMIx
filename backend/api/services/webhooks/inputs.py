"""What a webhook call's body gives the run it starts (pure, no I/O). Another app sends
whatever it sends, so the rules are few and predictable:

1. A JSON object with ``input`` or ``inputs`` is a run request, as
   ``POST /pipelines/<id>/runs`` takes it.
2. Otherwise a pipeline with named inputs takes the object's fields of those names,
   and each input's declared default where none is sent; one with a single named
   input takes the whole body when no field has its name.
3. Otherwise the body is the run's text: JSON laid out readably, anything else as sent.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from api.exceptions import ValidationFailed
from api.models import RunTrigger
from api.schemas.common import ensure_run_input_size
from api.schemas.pipelines import RunRequest
from api.services.run_plan import RunStart

#: The fields that make a call's JSON object a run request (rule 1).
REQUEST_KEYS = ("input", "inputs")


def call_start(fields: Sequence[Mapping[str, str]], body: bytes) -> RunStart:
    """The run one call starts, for a pipeline whose named inputs are ``fields``."""
    text = body.decode("utf-8", errors="replace").strip()
    payload = _json(text)
    if isinstance(payload, dict) and any(key in payload for key in REQUEST_KEYS):
        return _requested(payload)
    shown = text if payload is None else json.dumps(payload, indent=2, ensure_ascii=False)
    names = [field["name"] for field in fields]
    if not names:
        return _started(shown, {})
    if isinstance(payload, dict):
        values = {name: _as_text(payload[name]) for name in names if name in payload}
        if values or len(names) > 1:
            return _started("", _with_defaults(fields, values))
    if len(names) == 1:
        return _started("", {names[0]: shown})
    raise ValidationFailed(
        f"This workflow takes named inputs: send a JSON object with {', '.join(names)}."
    )


def _json(text: str) -> Any:
    """The body as JSON, or None when it is not JSON."""
    try:
        return json.loads(text)
    except ValueError:
        return None


def _requested(payload: Mapping[str, Any]) -> RunStart:
    try:
        request = RunRequest.model_validate(
            {key: payload[key] for key in REQUEST_KEYS if key in payload}
        )
    except ValueError as cause:
        raise ValidationFailed(
            'Send "input" as text, or "inputs" as an object of texts, within the run size.'
        ) from cause
    return _started(request.input, request.inputs)


def _started(text: str, values: Mapping[str, str]) -> RunStart:
    try:
        ensure_run_input_size(text, values)
    except ValueError as cause:
        raise ValidationFailed(str(cause)) from cause
    return RunStart(text, dict(values), trigger=RunTrigger.WEBHOOK)


def _with_defaults(fields: Sequence[Mapping[str, str]], sent: Mapping[str, str]) -> dict[str, str]:
    """The values sent, and each input's declared default where none was: another app
    cannot know every input a workflow declares."""
    defaults = {field["name"]: field.get("default_value", "") for field in fields}
    filled = {**defaults, **{name: value for name, value in sent.items() if value.strip()}}
    return {name: value for name, value in filled.items() if value.strip()}


def _as_text(value: Any) -> str:
    """A field's value as an input: text as it is, anything else as JSON."""
    if isinstance(value, str):
        return value
    return "" if value is None else json.dumps(value, ensure_ascii=False)

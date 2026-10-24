"""Header values of a user's MCP server: sealed at rest, never returned.

They are encrypted together as one JSON object with ``SecretBox`` (keyed from
SECRET_KEY, like provider API keys). The API only ever shows a header's name
and a hint: the last characters of a value long enough that the hint cannot
be the whole secret.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from api.exceptions import ValidationFailed
from api.models import API_KEY_HINT_LENGTH, Integration
from api.repositories.integrations import StoredHeaders
from api.security import SecretBox

#: Shorter values get no hint at all, so a hint never reveals a short secret.
HINT_MIN_VALUE_LENGTH = 3 * API_KEY_HINT_LENGTH


@dataclass(frozen=True)
class HeaderInput:
    """One header as a form sends it; ``value`` None keeps the saved value."""

    name: str
    value: str | None = None


def hint(value: str) -> str:
    return value[-API_KEY_HINT_LENGTH:] if len(value) >= HINT_MIN_VALUE_LENGTH else ""


def seal(box: SecretBox, headers: dict[str, str]) -> StoredHeaders:
    if not headers:
        return StoredHeaders(ciphertext="", hints=[])
    hints = [{"name": name, "hint": hint(value)} for name, value in headers.items()]
    return StoredHeaders(ciphertext=box.seal(json.dumps(headers)), hints=hints)


def reveal(box: SecretBox, integration: Integration) -> dict[str, str]:
    """The saved header values. Raises ``UnreadableSecret`` when SECRET_KEY changed."""
    if not integration.headers_encrypted:
        return {}
    values: dict[str, str] = json.loads(box.open(integration.headers_encrypted))
    return values


def merge(sent: list[HeaderInput], saved: dict[str, str]) -> dict[str, str]:
    """The headers to store: each sent value, or the saved value of a header sent
    without one. Names match case-insensitively, as HTTP header names do."""
    saved_by_name = {name.lower(): value for name, value in saved.items()}
    merged: dict[str, str] = {}
    for header in sent:
        value = header.value if header.value is not None else saved_by_name.get(header.name.lower())
        if value is None:
            raise ValidationFailed(f"Enter a value for the {header.name} header.")
        merged[header.name] = value
    return merged


def keeps_saved_values(sent: list[HeaderInput] | None) -> bool:
    """Whether a form asks to keep saved values: it left headers out, or sent one blank."""
    return sent is None or any(header.value is None for header in sent)

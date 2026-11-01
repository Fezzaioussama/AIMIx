"""The message each kind of address expects (§5 O, Strategy + Registry): Slack's and
Discord's incoming webhooks take a short text, anything else gets the run as JSON. A new
kind of address is one entry in ``KINDS``. Pure: no I/O."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RunMessage:
    """What a delivery says about one ended run (or, ``run_id`` None, about itself)."""

    workflow: str
    status: str
    text: str
    run_id: int | None = None


@dataclass(frozen=True)
class DeliveryKind:
    """One kind of address: how it is recognised, and the body it is sent."""

    label: str
    matches: Callable[[str, str], bool]
    body: Callable[[RunMessage, int], dict[str, Any]]


#: The headline of a message, by how the run ended.
HEADLINES = {
    "succeeded": "finished",
    "failed": "failed",
    "ready": "will send its results here",
}

#: What fits in one chat message of each service, with room for the headline.
SLACK_TEXT_MAX_CHARS = 3500
DISCORD_TEXT_MAX_CHARS = 1900


def headline(message: RunMessage) -> str:
    return f"{message.workflow} {HEADLINES.get(message.status, message.status)}"


def _chat_text(message: RunMessage, limit: int) -> str:
    """A headline, then as much of the result as one message holds."""
    text = f"{headline(message)}\n\n{message.text}".strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _json_body(message: RunMessage, max_chars: int) -> dict[str, Any]:
    return {
        "event": "run.ended" if message.run_id is not None else "delivery.confirmed",
        "run_id": message.run_id,
        "workflow": message.workflow,
        "status": message.status,
        "result": message.text[:max_chars],
    }


def _host_is(*hosts: str) -> Callable[[str, str], bool]:
    return lambda host, path: host in hosts


KINDS: dict[str, DeliveryKind] = {
    "slack": DeliveryKind(
        "Slack",
        _host_is("hooks.slack.com"),
        lambda message, _: {"text": _chat_text(message, SLACK_TEXT_MAX_CHARS)},
    ),
    "discord": DeliveryKind(
        "Discord",
        lambda host, path: (
            host in {"discord.com", "discordapp.com"} and path.startswith("/api/webhooks/")
        ),
        lambda message, _: {"content": _chat_text(message, DISCORD_TEXT_MAX_CHARS)},
    ),
    "json": DeliveryKind("Webhook", lambda host, path: True, _json_body),
}


def kind_of(url: str) -> str:
    """The kind of address ``url`` is; ``json`` when no other kind claims it."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return next(name for name, kind in KINDS.items() if kind.matches(host, parts.path))


def body_for(kind: str, message: RunMessage, max_chars: int) -> dict[str, Any]:
    """What is posted to an address of ``kind``; ``max_chars`` bounds a JSON result."""
    return KINDS[kind].body(message, max_chars)

"""The message each kind of address expects (§5 O, Strategy + Registry): Slack's and
Discord's incoming webhooks take a short text, an email address a subject and a text,
anything else gets the run as JSON. A new kind of address is one entry in ``KINDS``.
Pure: no I/O."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit

#: How an email address is kept: as a mailto link, so one column holds every kind.
MAILTO = "mailto:"


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
    #: Whether a split address is of this kind.
    matches: Callable[[SplitResult], bool]
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
#: The text of the first email, the one sent when the address is confirmed.
EMAIL_HELLO = "Each run of this workflow will send its result here, with the files it saved."


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


def _email_body(message: RunMessage, max_chars: int) -> dict[str, Any]:
    """The headline as the subject; the result (cut like a JSON one) as the text."""
    text = message.text[:max_chars] if message.run_id is not None else EMAIL_HELLO
    return {"subject": headline(message), "text": text}


def _host(parts: SplitResult) -> str:
    return (parts.hostname or "").lower()


def _host_is(*hosts: str) -> Callable[[SplitResult], bool]:
    return lambda parts: _host(parts) in hosts


KINDS: dict[str, DeliveryKind] = {
    "slack": DeliveryKind(
        "Slack",
        _host_is("hooks.slack.com"),
        lambda message, _: {"text": _chat_text(message, SLACK_TEXT_MAX_CHARS)},
    ),
    "discord": DeliveryKind(
        "Discord",
        lambda parts: (
            _host(parts) in {"discord.com", "discordapp.com"}
            and parts.path.startswith("/api/webhooks/")
        ),
        lambda message, _: {"content": _chat_text(message, DISCORD_TEXT_MAX_CHARS)},
    ),
    "email": DeliveryKind("Email", lambda parts: parts.scheme == "mailto", _email_body),
    "json": DeliveryKind("Webhook", lambda parts: True, _json_body),
}


def kind_of(url: str) -> str:
    """The kind of address ``url`` is; ``json`` when no other kind claims it."""
    parts = urlsplit(url)
    return next(name for name, kind in KINDS.items() if kind.matches(parts))


def body_for(kind: str, message: RunMessage, max_chars: int) -> dict[str, Any]:
    """What is posted to an address of ``kind``; ``max_chars`` bounds a JSON result."""
    return KINDS[kind].body(message, max_chars)

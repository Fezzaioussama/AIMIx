"""Chat tools that give a workflow a webhook, so another app can start it. The secret
link is never part of what they return: the chat screen shows it to the person from
``GET /webhooks/<id>``, so the model and its provider never read it (AGENTS.md §6)."""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session

from api.exceptions import DomainError
from api.security import secret_box_for
from api.services.chat_tools.common import refused, session_user
from api.services.chat_tools.scope import ChatScope
from api.services.webhooks import service
from api.services.webhooks.service import WebhookAccess, WebhookView
from config.settings import get_settings


def webhook_summary(view: WebhookView) -> dict[str, Any]:
    """A webhook as the chat tells it: its workflow, whether it is on, its last call."""
    return {
        "id": view.id,
        "workflow": view.pipeline_name,
        "on": view.enabled,
        "last_called_at": None if view.last_called_at is None else view.last_called_at.isoformat(),
        "last_error": view.last_error or None,
    }


def webhook_tools(scope: ChatScope) -> list[BaseTool]:
    """Bind the webhook tools to the signed-in person."""

    def access(session: Session) -> WebhookAccess:
        owner = session_user(session, scope.user)
        return WebhookAccess(session, owner, secret_box_for(get_settings()))

    @tool
    def create_webhook(pipeline_id: int) -> dict[str, Any]:
        """Give one of your workflows a webhook: a secret link another app (a form,
        Zapier, Make, your own code) calls to start a run, sending JSON or text as
        its input. A workflow that has one keeps it. The person sees the link on
        their screen; it is never in your reply."""
        try:
            with scope.database.session() as session:
                return webhook_summary(service.link_for(access(session), pipeline_id))
        except DomainError as cause:
            raise refused(cause) from cause

    @tool
    def list_webhooks() -> list[dict[str, Any]]:
        """List your webhooks: each one's workflow, whether it is on, and its last
        call and what went wrong with it, if anything."""
        with scope.database.session() as session:
            return [webhook_summary(view) for view in service.views(access(session))]

    @tool
    def set_webhook(webhook_id: int, on: bool) -> dict[str, Any]:
        """Switch a webhook off (its link then starts nothing) or on again."""
        try:
            with scope.database.session() as session:
                view = service.set_enabled(access(session), webhook_id, on)
                return webhook_summary(view)
        except DomainError as cause:
            raise refused(cause) from cause

    @tool
    def renew_webhook_link(webhook_id: int) -> dict[str, Any]:
        """Give a webhook a new secret link, when the old one was shared too widely.
        The old link stops working at once."""
        try:
            with scope.database.session() as session:
                return webhook_summary(service.renew(access(session), webhook_id))
        except DomainError as cause:
            raise refused(cause) from cause

    return [create_webhook, list_webhooks, set_webhook, renew_webhook_link]

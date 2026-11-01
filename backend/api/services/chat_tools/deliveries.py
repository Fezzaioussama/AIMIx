"""Chat tools that send a workflow's results to Slack, Discord or any webhook address
when a run ends. An address set here sends nothing until the person confirms it on
their screen (``POST /deliveries/<id>/confirm``): the chat can propose where results
go, never decide it (AGENTS.md §6)."""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session

from api.exceptions import DomainError
from api.security import secret_box_for
from api.services.chat_tools.common import refused, session_user
from api.services.chat_tools.scope import ChatScope
from api.services.deliveries import service
from api.services.deliveries.service import DeliveryAccess, DeliveryView
from config.settings import get_settings


def delivery_summary(view: DeliveryView) -> dict[str, Any]:
    """A delivery as the chat tells it: the address's host only, and its state."""
    return {
        "id": view.id,
        "workflow": view.pipeline_name,
        "destination": view.destination,
        "service": view.service,
        "confirmed": view.confirmed,
        "on": view.enabled,
        "last_sent_at": None if view.last_sent_at is None else view.last_sent_at.isoformat(),
        "last_error": view.last_error or None,
    }


def delivery_tools(scope: ChatScope) -> list[BaseTool]:
    """Bind the delivery tools to the signed-in person."""

    def access(session: Session) -> DeliveryAccess:
        owner = session_user(session, scope.user)
        return DeliveryAccess(session, owner, secret_box_for(get_settings()))

    @tool
    def send_results_to(pipeline_id: int, address: str) -> dict[str, Any]:
        """Post the results of one of your workflows to an address each time a run
        ends: a Slack or Discord webhook link the person gives you, or any https
        address (it gets JSON). It replaces the workflow's previous address. Nothing
        is sent until the person clicks Confirm on their screen; tell them so."""
        try:
            with scope.database.session() as session:
                view = service.set_address(access(session), pipeline_id, address)
                return delivery_summary(view)
        except DomainError as cause:
            raise refused(cause) from cause

    @tool
    def list_deliveries() -> list[dict[str, Any]]:
        """List where your workflows' results are sent: each address's host, whether
        the person confirmed it, whether it is on, and its last sending."""
        with scope.database.session() as session:
            return [delivery_summary(view) for view in service.views(access(session))]

    @tool
    def set_delivery(delivery_id: int, on: bool) -> dict[str, Any]:
        """Stop sending a workflow's results (on=false), or send them again to the
        address the person confirmed."""
        try:
            with scope.database.session() as session:
                view = service.set_enabled(access(session), delivery_id, on)
                return delivery_summary(view)
        except DomainError as cause:
            raise refused(cause) from cause

    return [send_results_to, list_deliveries, set_delivery]

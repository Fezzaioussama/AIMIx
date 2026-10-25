"""The Integrations use cases: each user's own MCP servers (Settings page).

A user connects remote MCP servers — a CRM, a database, company tools, an
automation hub — and their tools join the operator's MCP_SERVERS for that
user's agents only. Rules live in ``rules.py``, header values in
``headers.py``, and how agents connect in ``connections.py``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.sessions import Connection
from sqlalchemy.orm import Session

from api.exceptions import ToolUnavailable, ValidationFailed
from api.models import Integration, User
from api.repositories import integrations as repository
from api.repositories.integrations import IntegrationChanges, StoredHeaders
from api.security import SecretBox, UnreadableSecret
from api.services.integrations.connections import integration_connection
from api.services.integrations.headers import HeaderInput, keeps_saved_values, merge, reveal, seal
from api.services.integrations.rules import IntegrationRules, ensure_reachable, origin
from api.services.mcp_discovery import failure_kind, load_server_tools
from api.services.tool_catalog import describe

logger = logging.getLogger(__name__)

UNREADABLE_HEADERS = (
    "The saved header values can no longer be read, because the server's encryption "
    "key changed. Enter each value again."
)


@dataclass(frozen=True)
class IntegrationAccess:
    """The signed-in user's integrations, for one request (built in api/deps.py)."""

    session: Session
    user: User
    box: SecretBox
    rules: IntegrationRules


@dataclass(frozen=True)
class HeaderView:
    """A saved header as the API shows it: never its value."""

    name: str
    hint: str


@dataclass(frozen=True)
class IntegrationView:
    id: int
    name: str
    url: str
    enabled: bool
    headers: list[HeaderView]
    created_at: datetime
    #: In a run, its tools wait for the owner's OK before they act.
    require_approval: bool = True


@dataclass(frozen=True)
class IntegrationDraft:
    """A new integration; every header needs a value."""

    name: str
    url: str
    enabled: bool = True
    headers: list[HeaderInput] = field(default_factory=list)
    require_approval: bool = True


@dataclass(frozen=True)
class IntegrationEdit:
    """Changes to an integration; None keeps a field, and ``headers`` replaces
    the whole list, a header sent without a value keeping its saved one."""

    name: str | None = None
    url: str | None = None
    enabled: bool | None = None
    headers: list[HeaderInput] | None = None
    require_approval: bool | None = None


@dataclass(frozen=True)
class ToolView:
    name: str
    description: str


def _view(integration: Integration) -> IntegrationView:
    return IntegrationView(
        id=integration.id,
        name=integration.name,
        url=integration.url,
        enabled=integration.enabled,
        headers=[HeaderView(item["name"], item["hint"]) for item in integration.header_hints],
        created_at=integration.created_at,
        require_approval=integration.require_approval,
    )


def list_views(access: IntegrationAccess) -> list[IntegrationView]:
    return [_view(row) for row in repository.for_user(access.session, access.user)]


def _check_reserved(access: IntegrationAccess, name: str) -> None:
    if name in access.rules.reserved_names:
        raise ValidationFailed(f"The name {name} is used by a built-in server. Choose another.")


def _check_name(access: IntegrationAccess, name: str, ignore_id: int | None = None) -> None:
    _check_reserved(access, name)
    if repository.name_taken(access.session, access.user, name, ignore_id):
        raise ValidationFailed(f"You already have an integration named {name}.")


def _check_address(access: IntegrationAccess, url: str) -> None:
    rules = access.rules
    asyncio.run(ensure_reachable(url, rules.addresses, rules.timeout_seconds))


def create(access: IntegrationAccess, draft: IntegrationDraft) -> IntegrationView:
    limit = access.rules.max_per_user
    if repository.count(access.session, access.user) >= limit:
        raise ValidationFailed(f"You can connect up to {limit} integrations. Delete one first.")
    _check_name(access, draft.name)
    _check_address(access, draft.url)
    headers = seal(access.box, merge(draft.headers, {}))
    changes = IntegrationChanges(
        draft.name, draft.url, draft.enabled, headers, require_approval=draft.require_approval
    )
    row = repository.create(access.session, access.user, changes)
    # Counts only: neither header values nor their hints reach the logs (§6).
    logger.info(
        "integration.created user_id=%s integration_id=%s headers=%d",
        access.user.id,
        row.id,
        len(headers.hints),
    )
    return _view(row)


def _saved_headers(access: IntegrationAccess, row: Integration) -> dict[str, str]:
    try:
        return reveal(access.box, row)
    except UnreadableSecret as cause:
        raise ValidationFailed(UNREADABLE_HEADERS) from cause


def _new_headers(
    access: IntegrationAccess, row: Integration, edit: IntegrationEdit
) -> StoredHeaders | None:
    # Saved values only ever go to the server they were entered for.
    moved = edit.url is not None and origin(edit.url) != origin(row.url)
    if moved and row.header_hints and keeps_saved_values(edit.headers):
        raise ValidationFailed(
            "You changed the server's address: enter every header value again, "
            "so saved values never go to a different server."
        )
    if edit.headers is None:
        return None
    saved = _saved_headers(access, row) if keeps_saved_values(edit.headers) else {}
    return seal(access.box, merge(edit.headers, saved))


def update(
    access: IntegrationAccess, integration_id: int, edit: IntegrationEdit
) -> IntegrationView:
    """Apply an edit. Sending the same edit twice leaves the same state."""
    row = repository.get_owned(access.session, access.user, integration_id)
    if edit.name is not None and edit.name != row.name:
        _check_name(access, edit.name, row.id)
    if edit.url is not None:
        _check_address(access, edit.url)
    headers = _new_headers(access, row, edit)
    changes = IntegrationChanges(
        edit.name, edit.url, edit.enabled, headers, require_approval=edit.require_approval
    )
    repository.update(access.session, row, changes)
    logger.info(
        "integration.updated user_id=%s integration_id=%s headers_replaced=%s",
        access.user.id,
        row.id,
        headers is not None,
    )
    return _view(row)


def delete(access: IntegrationAccess, integration_id: int) -> None:
    row = repository.get_owned(access.session, access.user, integration_id)
    repository.delete(access.session, row)
    logger.info("integration.deleted user_id=%s integration_id=%s", access.user.id, integration_id)


def _connection(access: IntegrationAccess, row: Integration) -> Connection:
    _check_reserved(access, row.name)
    try:
        return integration_connection(row, access.box, access.rules)
    except UnreadableSecret as cause:
        raise ValidationFailed(UNREADABLE_HEADERS) from cause


async def _probe(
    row: Integration, connection: Connection, rules: IntegrationRules
) -> list[BaseTool]:
    await ensure_reachable(row.url, rules.addresses, rules.timeout_seconds)
    return await load_server_tools(row.name, connection, rules.timeout_seconds)


def test_connection(access: IntegrationAccess, integration_id: int) -> list[ToolView]:
    """Connect within MCP_TIMEOUT_SECONDS and list the tools agents would get."""
    row = repository.get_owned(access.session, access.user, integration_id)
    connection = _connection(access, row)
    started = monotonic()
    try:
        tools = asyncio.run(_probe(row, connection, access.rules))
    except ToolUnavailable as cause:
        logger.warning(
            "integration.test_failed user_id=%s integration_id=%s error=%s",
            access.user.id,
            row.id,
            failure_kind(cause),
        )
        raise
    logger.info(
        "integration.tested user_id=%s integration_id=%s tools=%d duration_ms=%.1f",
        access.user.id,
        row.id,
        len(tools),
        (monotonic() - started) * 1000,
    )
    limit = access.rules.description_max_chars
    return [ToolView(item.name, describe(item, limit)) for item in tools]

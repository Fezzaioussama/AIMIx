"""OAuth sign-in to a user's MCP server (Settings → Integrations → "Sign in with
OAuth"): the authorization-code flow with PKCE the MCP authorization spec describes,
driven from the server so no token ever reaches the browser.

``begin`` finds the server's authorization server (its protected-resource metadata,
else the server's own origin), registers AIMIx as a client there (dynamic client
registration; a server without it cannot be connected this way), keeps the attempt
sealed on the integration and gives the URL the owner's browser opens. The
authorization server sends the owner back to CALLBACK_PATH with a code: ``finish``
trades it for tokens, sealed on the integration too, and ``landing_url`` says where
the browser goes next. From then on every connection signs its requests with the
access token (``bearer.OAuthBearer``). Every HTTP call here goes through the guarded
client: public addresses only, bounded answers, no redirect (AGENTS.md §6).
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

import httpx
from anyio import to_thread
from mcp.client.auth.exceptions import OAuthFlowError
from mcp.client.auth.oauth2 import PKCEParameters
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_client_registration_request,
    create_oauth_metadata_request,
    handle_auth_metadata_response,
    handle_protected_resource_response,
    handle_registration_response,
)
from mcp.shared.auth import OAuthClientMetadata, OAuthMetadata
from mcp.shared.auth_utils import resource_url_from_server_url
from pydantic import AnyUrl

from api.db import Database
from api.exceptions import ValidationFailed
from api.models import Integration
from api.repositories import integrations as repository
from api.security import SecretBox, UnreadableSecret
from api.services.addresses import AddressNotAllowed
from api.services.integrations.oauth_tokens import (
    CONNECTED,
    NONE,
    PENDING,
    Attempt,
    Client,
    Tokens,
    answered_token,
    attempt_of,
    exchange_request,
    seal,
    tokens_from,
)
from api.services.integrations.rules import IntegrationRules, ensure_reachable
from api.services.integrations.service import IntegrationAccess, IntegrationView, view_of
from api.services.outbound import OutboundPolicy, guarded_client, guarded_transport
from api.services.secret_links import token_hash
from config.settings import Settings

logger = logging.getLogger(__name__)

#: Where the authorization server sends the owner back, on the API.
CALLBACK_PATH = "/api/integrations/oauth/callback"
#: Where the owner lands afterwards, on the app, told how it went.
SETTINGS_PATH = "/settings/integrations"
CLIENT_NAME = "AIMIx"
NO_REGISTRATION = (
    "This server's authorization server does not accept new clients, so it cannot be "
    "connected with OAuth. Use its headers instead."
)
UNMATCHED = "This sign-in could not be matched to an integration. Start it again."
TOO_LATE = "The sign-in took too long. Start it again."
#: What begin and finish catch from the wire and the SDK, to say in the owner's words.
WIRE_FAILURES = (httpx.HTTPError, AddressNotAllowed, OAuthFlowError)


@dataclass(frozen=True)
class OAuthPolicy:
    """How a sign-in runs: where the authorization server sends the owner back, where
    they land afterwards, how long an attempt lasts, and how the server's endpoints are
    reached (the guarded transport, unless a test passes another)."""

    callback_url: str
    app_url: str
    attempt_seconds: float
    timeout_seconds: float
    transport: Callable[[], httpx.AsyncBaseTransport]


def oauth_policy(settings: Settings, rules: IntegrationRules) -> OAuthPolicy:
    addresses = rules.addresses
    outbound = OutboundPolicy(addresses.resolver, addresses.allow_private, rules.max_response_bytes)
    return OAuthPolicy(
        callback_url=f"{settings.app_public_url}{CALLBACK_PATH}",
        app_url=settings.app_public_url,
        attempt_seconds=settings.integrations_oauth_attempt_minutes * 60,
        timeout_seconds=rules.timeout_seconds,
        transport=lambda: guarded_transport(outbound),
    )


@dataclass(frozen=True)
class Callback:
    """What the authorization server sent back with the owner."""

    code: str
    state: str
    error: str = ""


@dataclass(frozen=True)
class Outcome:
    """How a sign-in ended: the integration's name, or why it failed, in the owner's words."""

    connected: str = ""
    error: str = ""


def _client(policy: OAuthPolicy) -> httpx.AsyncClient:
    return guarded_client(
        policy.transport(), timeout=policy.timeout_seconds, follow_redirects=False
    )


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


async def _metadata(client: httpx.AsyncClient, server_url: str) -> tuple[OAuthMetadata | None, str]:
    """The authorization server's metadata and base URL: the server named by the MCP
    server's protected-resource metadata, else the MCP server's own origin."""
    auth_server: str | None = None
    for url in build_protected_resource_metadata_discovery_urls(None, server_url):
        response = await client.send(create_oauth_metadata_request(url))
        resource = await handle_protected_resource_response(response)
        if resource is not None and resource.authorization_servers:
            auth_server = str(resource.authorization_servers[0])
            break
    for url in build_oauth_authorization_server_metadata_discovery_urls(auth_server, server_url):
        response = await client.send(create_oauth_metadata_request(url))
        keep_looking, metadata = await handle_auth_metadata_response(response)
        if metadata is not None or not keep_looking:
            return metadata, auth_server or _origin(server_url)
    return None, auth_server or _origin(server_url)


def _client_metadata(callback_url: str) -> OAuthClientMetadata:
    return OAuthClientMetadata(
        client_name=CLIENT_NAME,
        redirect_uris=[AnyUrl(callback_url)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )


async def _register(
    client: httpx.AsyncClient, metadata: OAuthMetadata | None, base: str, callback_url: str
) -> Client:
    """AIMIx as a client of the authorization server, registered dynamically (RFC 7591)."""
    if metadata is None or metadata.registration_endpoint is None:
        raise ValidationFailed(NO_REGISTRATION)
    request = create_client_registration_request(metadata, _client_metadata(callback_url), base)
    info = await handle_registration_response(await client.send(request))
    if not info.client_id:
        raise ValidationFailed("The authorization server registered no client id.")
    return Client(
        info.client_id,
        str(metadata.token_endpoint),
        str(metadata.authorization_endpoint),
        info.client_secret or "",
    )


def _authorization_url(attempt: Attempt, code_challenge: str, callback_url: str) -> str:
    query = {
        "response_type": "code",
        "client_id": attempt.client.client_id,
        "redirect_uri": callback_url,
        "state": attempt.state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": attempt.resource,
    }
    return f"{attempt.client.authorization_endpoint}?{urlencode(query)}"


def _keep_attempt(access: IntegrationAccess, row: Integration, attempt: Attempt) -> None:
    repository.set_oauth(
        access.session, row, PENDING, seal(access.box, attempt), token_hash(attempt.state)
    )


async def begin(access: IntegrationAccess, integration_id: int, policy: OAuthPolicy) -> str:
    """Start the owner's sign-in; the URL their browser opens."""
    row = await to_thread.run_sync(
        repository.get_owned, access.session, access.user, integration_id
    )
    await ensure_reachable(row.url, access.rules.addresses, access.rules.timeout_seconds)
    try:
        async with _client(policy) as client:
            metadata, base = await _metadata(client, row.url)
            registered = await _register(client, metadata, base, policy.callback_url)
    except WIRE_FAILURES as cause:
        raise ValidationFailed(
            f"The server's sign-in could not be set up ({type(cause).__name__})."
        ) from cause
    pkce = PKCEParameters.generate()
    attempt = Attempt(
        secrets.token_urlsafe(32),
        pkce.code_verifier,
        resource_url_from_server_url(row.url),
        time.time() + policy.attempt_seconds,
        registered,
    )
    await to_thread.run_sync(_keep_attempt, access, row, attempt)
    logger.info("integration.oauth_started user_id=%s integration_id=%s", access.user.id, row.id)
    return _authorization_url(attempt, pkce.code_challenge, policy.callback_url)


def _matched(database: Database, box: SecretBox, state: str) -> tuple[int, str, Attempt] | None:
    """The integration the call back is about, its name and its attempt; None when
    no sign-in matches or the attempt cannot be read."""
    with database.session() as session:
        row = repository.by_oauth_state(session, token_hash(state))
        if row is None:
            return None
        try:
            return row.id, row.name, attempt_of(box, row)
        except (UnreadableSecret, ValueError, TypeError):
            return None


async def _exchange(policy: OAuthPolicy, attempt: Attempt, code: str) -> Tokens:
    async with _client(policy) as client:
        response = await client.send(exchange_request(attempt, code, policy.callback_url))
    answered = answered_token(response)
    if answered is None:
        raise ValidationFailed(f"the token endpoint answered {response.status_code}")
    return tokens_from(answered, attempt.resource, attempt.client)


def _keep_tokens(database: Database, box: SecretBox, integration_id: int, tokens: Tokens) -> None:
    with database.session() as session:
        row = session.get(Integration, integration_id)
        if row is not None:
            repository.set_oauth(session, row, CONNECTED, seal(box, tokens), None)


async def finish(
    database: Database, box: SecretBox, policy: OAuthPolicy, back: Callback
) -> Outcome:
    """The authorization server's call back: trade the code for tokens and keep them.
    Never raises; the outcome says what the owner is told."""
    if back.error or not back.code or not back.state:
        return Outcome(error=f"The sign-in was refused ({back.error or 'no code came back'}).")
    matched = _matched(database, box, back.state)
    if matched is None:
        return Outcome(error=UNMATCHED)
    integration_id, name, attempt = matched
    if time.time() > attempt.expires_at:
        return Outcome(error=TOO_LATE)
    try:
        tokens = await _exchange(policy, attempt, back.code)
    except (*WIRE_FAILURES, ValidationFailed) as cause:
        detail = cause.detail if isinstance(cause, ValidationFailed) else type(cause).__name__
        return Outcome(error=f"The server did not hand over a token ({detail}).")
    await to_thread.run_sync(_keep_tokens, database, box, integration_id, tokens)
    logger.info("integration.oauth_connected integration_id=%s", integration_id)
    return Outcome(connected=name)


def landing_url(policy: OAuthPolicy, outcome: Outcome) -> str:
    """Where the owner's browser goes next: Settings → Integrations, told how it went."""
    query = (
        {"connected": outcome.connected} if outcome.connected else {"oauth_error": outcome.error}
    )
    return f"{policy.app_url}{SETTINGS_PATH}?{urlencode(query)}"


def forget(access: IntegrationAccess, integration_id: int) -> IntegrationView:
    """Sign out: the tokens (or the attempt) are forgotten; headers, if any, stay."""
    row = repository.get_owned(access.session, access.user, integration_id)
    repository.set_oauth(access.session, row, NONE, "", None)
    logger.info("integration.oauth_forgotten user_id=%s integration_id=%s", access.user.id, row.id)
    return view_of(row)

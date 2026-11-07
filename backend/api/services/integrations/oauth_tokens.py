"""What an OAuth sign-in to a user's MCP server leaves behind, sealed on the integration
(``Integration.oauth_encrypted``): while the owner signs in, the ``Attempt``; once done,
the ``Tokens``. Plain values and the token requests; the flow is ``oauth``, the signing
of requests ``bearer``."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from mcp.shared.auth import OAuthToken
from pydantic import ValidationError

from api.db import Database
from api.models import Integration
from api.repositories import integrations as repository
from api.security import SecretBox

#: The ``oauth_status`` of an integration.
NONE, PENDING, CONNECTED = "", "pending", "connected"
#: Seconds before its expiry an access token counts as expired, so a request never
#: reaches the server with a token about to lapse.
EXPIRY_SLACK_SECONDS = 30.0
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@dataclass(frozen=True)
class Client:
    """AIMIx as the authorization server registered it, and where to talk to it."""

    client_id: str
    token_endpoint: str
    authorization_endpoint: str
    client_secret: str = ""


@dataclass(frozen=True)
class Attempt:
    """A sign-in under way: what the call back needs to finish it."""

    state: str
    code_verifier: str
    resource: str
    expires_at: float
    client: Client


@dataclass(frozen=True)
class Tokens:
    """A finished sign-in: the access token, how to renew it, and for which server."""

    access_token: str
    refresh_token: str
    expires_at: float | None
    resource: str
    client: Client

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at - EXPIRY_SLACK_SECONDS


def seal(box: SecretBox, value: Attempt | Tokens) -> str:
    return box.seal(json.dumps(asdict(value)))


def _opened(box: SecretBox, integration: Integration) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(box.open(integration.oauth_encrypted))
    return {**data, "client": Client(**data["client"])}


def attempt_of(box: SecretBox, integration: Integration) -> Attempt:
    """The sign-in under way. Raises ``UnreadableSecret`` when SECRET_KEY changed."""
    return Attempt(**_opened(box, integration))


def tokens_of(box: SecretBox, integration: Integration) -> Tokens:
    """The tokens of a connected integration. Raises ``UnreadableSecret`` likewise."""
    return Tokens(**_opened(box, integration))


def tokens_from(
    answered: OAuthToken, resource: str, client: Client, previous: Tokens | None = None
) -> Tokens:
    """The tokens a token endpoint answered, keeping the refresh token it did not renew."""
    refresh = answered.refresh_token or (previous.refresh_token if previous else "")
    expires_at = time.time() + answered.expires_in if answered.expires_in else None
    return Tokens(answered.access_token, refresh or "", expires_at, resource, client)


def _with_secret(data: dict[str, str], client: Client) -> dict[str, str]:
    return {**data, "client_secret": client.client_secret} if client.client_secret else data


def exchange_request(attempt: Attempt, code: str, callback_url: str) -> httpx.Request:
    """The request that trades the authorization code for tokens (RFC 6749 §4.1.3,
    PKCE, RFC 8707 resource)."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_url,
        "client_id": attempt.client.client_id,
        "code_verifier": attempt.code_verifier,
        "resource": attempt.resource,
    }
    return httpx.Request(
        "POST", attempt.client.token_endpoint, data=_with_secret(data, attempt.client), headers=FORM
    )


def refresh_request(tokens: Tokens) -> httpx.Request:
    """The request that renews the access token (RFC 6749 §6, RFC 8707 resource)."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens.refresh_token,
        "client_id": tokens.client.client_id,
        "resource": tokens.resource,
    }
    return httpx.Request(
        "POST", tokens.client.token_endpoint, data=_with_secret(data, tokens.client), headers=FORM
    )


def answered_token(response: httpx.Response) -> OAuthToken | None:
    """The token a token endpoint answered, or None when it refused or made no sense."""
    if response.status_code != 200:
        return None
    try:
        return OAuthToken.model_validate_json(response.content)
    except ValidationError:
        return None


def renewed_tokens(tokens: Tokens, response: httpx.Response) -> Tokens | None:
    """The renewed tokens, or None when the server refused (the old ones stay)."""
    answered = answered_token(response)
    return (
        None if answered is None else tokens_from(answered, tokens.resource, tokens.client, tokens)
    )


#: Keeps renewed tokens, so the next connection starts fresh.
Renew = Any


def renew(database: Database, box: SecretBox, integration_id: int, tokens: Tokens) -> None:
    """Keep the renewed tokens of a connected integration (``OAuthBearer`` calls it)."""
    with database.session() as session:
        row = session.get(Integration, integration_id)
        if row is not None and row.oauth_status == CONNECTED:
            repository.set_oauth(session, row, CONNECTED, seal(box, tokens), None)

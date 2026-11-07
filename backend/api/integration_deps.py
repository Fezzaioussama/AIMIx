"""The integrations' part of ``deps.py``: the signed-in user's own MCP servers (Settings →
Integrations), the host-name lookup their address checks use, and their OAuth sign-in.
Tests swap these functions through ``app.dependency_overrides`` like any other
dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from api.db import Database
from api.deps import AppSettings, CurrentUser, DbSession, Secrets
from api.security import SecretBox
from api.services.addresses import Resolver, resolve_host
from api.services.integrations.oauth import OAuthPolicy, oauth_policy
from api.services.integrations.rules import IntegrationRules, rules_from
from api.services.integrations.service import IntegrationAccess


def host_resolver() -> Resolver:
    """How the integration address checks resolve host names; tests swap in a fake."""
    return resolve_host


def integration_rules(
    settings: AppSettings, resolver: Annotated[Resolver, Depends(host_resolver)]
) -> IntegrationRules:
    return rules_from(settings, resolver)


def integration_access(
    user: CurrentUser,
    session: DbSession,
    box: Secrets,
    rules: Annotated[IntegrationRules, Depends(integration_rules)],
) -> IntegrationAccess:
    """The signed-in user's integrations (Settings → Integrations)."""
    return IntegrationAccess(session, user, box, rules)


Integrations = Annotated[IntegrationAccess, Depends(integration_access)]


def oauth_sign_in(
    settings: AppSettings, rules: Annotated[IntegrationRules, Depends(integration_rules)]
) -> OAuthPolicy:
    """How an integration's OAuth sign-in runs (APP_PUBLIC_URL,
    INTEGRATIONS_OAUTH_ATTEMPT_MINUTES, the guarded transport); tests swap the transport."""
    return oauth_policy(settings, rules)


OAuthSignIn = Annotated[OAuthPolicy, Depends(oauth_sign_in)]


@dataclass(frozen=True)
class OAuthReturn:
    """What the authorization server's call back needs: the database (the sign-in is
    found by its state, in its own session), the box and the policy."""

    database: Database
    box: SecretBox
    policy: OAuthPolicy


def oauth_return(request: Request, box: Secrets, policy: OAuthSignIn) -> OAuthReturn:
    return OAuthReturn(request.app.state.database, box, policy)


OAuthReturns = Annotated[OAuthReturn, Depends(oauth_return)]

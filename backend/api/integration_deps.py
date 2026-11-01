"""The integrations' part of ``deps.py``: the signed-in user's own MCP servers (Settings →
Integrations) and the host-name lookup their address checks use. Tests swap these
functions through ``app.dependency_overrides`` like any other dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from api.deps import AppSettings, CurrentUser, DbSession, Secrets
from api.services.addresses import Resolver, resolve_host
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

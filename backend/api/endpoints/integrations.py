"""The signed-in user's own MCP servers (Settings → Integrations), and their OAuth
sign-in: started by the owner, finished by the authorization server's call back
(public: the owner arrives there from the server, the state naming the sign-in). Each
endpoint validates, calls the service and shapes the result (AGENTS.md §2).

Saving, testing and starting a sign-in reach the network, so they are rate-limited
per account (``user_rate_limit``) and async: the service awaits the lookup and the
connection test instead of holding a worker thread for MCP_TIMEOUT_SECONDS.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse

from api.integration_deps import Integrations, OAuthReturns, OAuthSignIn
from api.schemas.integrations import (
    HeaderIn,
    IntegrationIn,
    IntegrationOut,
    IntegrationPatch,
    IntegrationTestOut,
    IntegrationToolOut,
    OAuthStartOut,
)
from api.services.integrations import oauth, service
from api.services.integrations.headers import HeaderInput
from api.throttling import user_rate_limit

router = APIRouter(prefix="/integrations", tags=["integrations"])
public_router = APIRouter(tags=["integrations"])

#: Routes that make the server reach out: one counter per account and route.
RATE_LIMITED = [Depends(user_rate_limit)]


def _headers(headers: list[HeaderIn] | None) -> list[HeaderInput] | None:
    if headers is None:
        return None
    return [HeaderInput(header.name, header.value) for header in headers]


@router.get("")
def list_integrations(access: Integrations) -> list[IntegrationOut]:
    return [IntegrationOut.model_validate(view) for view in service.list_views(access)]


@router.post("", status_code=201, dependencies=RATE_LIMITED)
async def create_integration(body: IntegrationIn, access: Integrations) -> IntegrationOut:
    draft = service.IntegrationDraft(
        body.name,
        body.url,
        body.enabled,
        _headers(body.headers) or [],
        require_approval=body.require_approval,
    )
    return IntegrationOut.model_validate(await service.create(access, draft))


@router.patch("/{integration_id}", dependencies=RATE_LIMITED)
async def update_integration(
    integration_id: int, body: IntegrationPatch, access: Integrations
) -> IntegrationOut:
    edit = service.IntegrationEdit(
        body.name,
        body.url,
        body.enabled,
        _headers(body.headers),
        require_approval=body.require_approval,
    )
    return IntegrationOut.model_validate(await service.update(access, integration_id, edit))


@router.delete("/{integration_id}", status_code=204)
def delete_integration(integration_id: int, access: Integrations) -> Response:
    service.delete(access, integration_id)
    return Response(status_code=204)


@router.post("/{integration_id}/test", dependencies=RATE_LIMITED)
async def test_integration(integration_id: int, access: Integrations) -> IntegrationTestOut:
    tools = await service.test_connection(access, integration_id)
    return IntegrationTestOut(tools=[IntegrationToolOut.model_validate(tool) for tool in tools])


@router.post("/{integration_id}/oauth", dependencies=RATE_LIMITED)
async def start_oauth(
    integration_id: int, access: Integrations, policy: OAuthSignIn
) -> OAuthStartOut:
    """Start the owner's OAuth sign-in to the server; their browser opens the URL."""
    return OAuthStartOut(authorization_url=await oauth.begin(access, integration_id, policy))


@router.delete("/{integration_id}/oauth")
def forget_oauth(integration_id: int, access: Integrations) -> IntegrationOut:
    """Sign out: the tokens are forgotten; the server's headers, if any, stay."""
    return IntegrationOut.model_validate(oauth.forget(access, integration_id))


@public_router.get("/integrations/oauth/callback", response_class=RedirectResponse)
async def oauth_callback(
    back: OAuthReturns, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    """Where the authorization server sends the owner back; they land on Settings →
    Integrations, told how it went. Public: the state names the sign-in."""
    outcome = await oauth.finish(
        back.database, back.box, back.policy, oauth.Callback(code, state, error)
    )
    return RedirectResponse(oauth.landing_url(back.policy, outcome), status_code=303)

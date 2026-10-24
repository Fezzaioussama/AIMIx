"""The signed-in user's own MCP servers (Settings → Integrations). Each endpoint
validates, calls the service and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from api.deps import Integrations
from api.schemas.integrations import (
    HeaderIn,
    IntegrationIn,
    IntegrationOut,
    IntegrationPatch,
    IntegrationTestOut,
    IntegrationToolOut,
)
from api.services.integrations import service
from api.services.integrations.headers import HeaderInput

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _headers(headers: list[HeaderIn] | None) -> list[HeaderInput] | None:
    if headers is None:
        return None
    return [HeaderInput(header.name, header.value) for header in headers]


@router.get("")
def list_integrations(access: Integrations) -> list[IntegrationOut]:
    return [IntegrationOut.model_validate(view) for view in service.list_views(access)]


@router.post("", status_code=201)
def create_integration(body: IntegrationIn, access: Integrations) -> IntegrationOut:
    draft = service.IntegrationDraft(
        body.name, body.url, body.enabled, _headers(body.headers) or []
    )
    return IntegrationOut.model_validate(service.create(access, draft))


@router.patch("/{integration_id}")
def update_integration(
    integration_id: int, body: IntegrationPatch, access: Integrations
) -> IntegrationOut:
    edit = service.IntegrationEdit(body.name, body.url, body.enabled, _headers(body.headers))
    return IntegrationOut.model_validate(service.update(access, integration_id, edit))


@router.delete("/{integration_id}", status_code=204)
def delete_integration(integration_id: int, access: Integrations) -> Response:
    service.delete(access, integration_id)
    return Response(status_code=204)


@router.post("/{integration_id}/test")
def test_integration(integration_id: int, access: Integrations) -> IntegrationTestOut:
    tools = service.test_connection(access, integration_id)
    return IntegrationTestOut(tools=[IntegrationToolOut.model_validate(tool) for tool in tools])

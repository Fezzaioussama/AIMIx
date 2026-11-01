"""Webhooks: another app starts a run by calling a secret link (public). Their owner lists
them, switches one off or on, renews or deletes its link (Settings → Webhooks), and reads
one with its link (the chat's link card, the screen's Copy link). Making one happens by
chat (``services/chat_tools/webhooks.py``)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from api.schemas.webhooks import WebhookCallOut, WebhookLinkOut, WebhookOut, WebhookPatch
from api.services.webhooks import service
from api.webhook_deps import WebhookCallers, Webhooks

public_router = APIRouter(tags=["webhooks"])
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@public_router.post("/hooks/{token}", status_code=202)
async def call_webhook(token: str, request: Request, calls: WebhookCallers) -> WebhookCallOut:
    """Queue a run of the webhook's pipeline with what the body sends, any JSON or text
    (``services/webhooks/inputs``). Public: the token in the path is the credential."""
    body = await request.body()
    run_id = await run_in_threadpool(calls.trigger, token, body)
    return WebhookCallOut(run_id=run_id)


@router.get("")
def list_webhooks(access: Webhooks) -> list[WebhookOut]:
    return [WebhookOut.model_validate(view) for view in service.views(access)]


@router.get("/{webhook_id}")
def get_webhook(webhook_id: int, access: Webhooks) -> WebhookLinkOut:
    link = service.link_of(access, webhook_id)
    return WebhookLinkOut.model_validate({**asdict(link.view), "token": link.token})


@router.patch("/{webhook_id}")
def update_webhook(webhook_id: int, body: WebhookPatch, access: Webhooks) -> WebhookOut:
    return WebhookOut.model_validate(service.set_enabled(access, webhook_id, body.enabled))


@router.post("/{webhook_id}/renew")
def renew_webhook(webhook_id: int, access: Webhooks) -> WebhookOut:
    """A new link; the old one stops working at once."""
    return WebhookOut.model_validate(service.renew(access, webhook_id))


@router.delete("/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: int, access: Webhooks) -> Response:
    service.remove(access, webhook_id)
    return Response(status_code=204)

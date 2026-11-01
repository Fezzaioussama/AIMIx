"""Webhooks: another app starts a run by calling a secret link (public), and its owner
reads one webhook with its link (the chat's link card). Making, switching and renewing
a webhook happen by chat (``services/chat_tools/webhooks.py``)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from api.deps import CurrentUser, DbSession, Secrets
from api.schemas.webhooks import WebhookCallOut, WebhookLinkOut
from api.services.webhooks import service
from api.services.webhooks.service import WebhookAccess
from api.webhook_deps import WebhookCallers

public_router = APIRouter(tags=["webhooks"])
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@public_router.post("/hooks/{token}", status_code=202)
async def call_webhook(token: str, request: Request, calls: WebhookCallers) -> WebhookCallOut:
    """Queue a run of the webhook's pipeline with what the body sends, any JSON or text
    (``services/webhooks/inputs``). Public: the token in the path is the credential."""
    body = await request.body()
    run_id = await run_in_threadpool(calls.trigger, token, body)
    return WebhookCallOut(run_id=run_id)


@router.get("/{webhook_id}")
def get_webhook(
    webhook_id: int, user: CurrentUser, session: DbSession, box: Secrets
) -> WebhookLinkOut:
    link = service.link_of(WebhookAccess(session, user, box), webhook_id)
    return WebhookLinkOut.model_validate({**asdict(link.view), "token": link.token})

"""The webhooks' part of ``deps.py``: another app calling a pipeline's webhook link, and a
run's results posted to another app's webhook address (result deliveries). Tests swap
these functions through ``app.dependency_overrides`` like any other dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from api.deps import AppSettings, Runs, Secrets
from api.services.deliveries.sender import SendPolicy, send_policy
from api.services.schedules.scheduler import ProfileAgents
from api.services.webhooks.calls import CallPolicy, WebhookCalls


def webhook_calls(
    request: Request, runs: Runs, box: Secrets, settings: AppSettings
) -> WebhookCalls:
    """Calls of webhooks by other apps: each run starts as the webhook's owner, on
    their own key, like a schedule's (``ProfileAgents``)."""
    database = request.app.state.database
    policy = CallPolicy(
        settings.secret_key,
        settings.webhook_rate_limit_requests,
        settings.webhook_rate_limit_window_seconds,
    )
    return WebhookCalls(database, runs, ProfileAgents(database, box), policy)


WebhookCallers = Annotated[WebhookCalls, Depends(webhook_calls)]


def delivery_sending(settings: AppSettings) -> SendPolicy:
    """How a delivery's first message is posted (DELIVERY_*); tests swap the transport."""
    return send_policy(settings)


DeliverySending = Annotated[SendPolicy, Depends(delivery_sending)]

"""A person's webhooks (the chat's tools, Settings → Webhooks): give a pipeline its
secret link, switch it off or on, renew it or delete it. The token is made here and
handed only to its owner's screen; the chat's model never reads it (AGENTS.md §6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from api.models import User, Webhook
from api.repositories import pipelines as pipeline_repository
from api.repositories import webhooks as repository
from api.security import SecretBox
from api.services.secret_links import new_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookAccess:
    """The signed-in user's webhooks, and the box their tokens are sealed in."""

    session: Session
    user: User
    box: SecretBox


@dataclass(frozen=True)
class WebhookView:
    """A webhook as its owner sees it, without its token."""

    id: int
    pipeline_id: int
    pipeline_name: str
    enabled: bool
    last_called_at: datetime | None
    last_error: str


@dataclass(frozen=True)
class WebhookLink:
    """A webhook and its token, for its owner's screen only."""

    view: WebhookView
    token: str


def view_of(webhook: Webhook) -> WebhookView:
    return WebhookView(
        id=webhook.id,
        pipeline_id=webhook.pipeline_id,
        pipeline_name=webhook.pipeline.name,
        enabled=webhook.enabled,
        last_called_at=webhook.last_called_at,
        last_error=webhook.last_error,
    )


def _sealed_token(box: SecretBox) -> tuple[str, str]:
    made = new_token(box)
    return made.hash, made.sealed


def link_for(access: WebhookAccess, pipeline_id: int) -> WebhookView:
    """The webhook of one of the user's pipelines, made (and on) when it has none."""
    pipeline = pipeline_repository.get_owned(access.session, access.user, pipeline_id)
    webhook = repository.of_pipeline(access.session, pipeline)
    if webhook is None:
        webhook = repository.create(access.session, pipeline, *_sealed_token(access.box))
        logger.info("webhook.created webhook_id=%s pipeline_id=%s", webhook.id, pipeline.id)
    return view_of(webhook)


def views(access: WebhookAccess) -> list[WebhookView]:
    return [view_of(webhook) for webhook in repository.for_user(access.session, access.user)]


def set_enabled(access: WebhookAccess, webhook_id: int, enabled: bool) -> WebhookView:
    """Switch a webhook off (its link answers like an unknown one) or on again."""
    webhook = repository.get_owned(access.session, access.user, webhook_id)
    repository.set_enabled(access.session, webhook, enabled)
    return view_of(webhook)


def renew(access: WebhookAccess, webhook_id: int) -> WebhookView:
    """Give a webhook a new token: the old link stops working at once."""
    webhook = repository.get_owned(access.session, access.user, webhook_id)
    repository.set_token(access.session, webhook, *_sealed_token(access.box))
    logger.info("webhook.renewed webhook_id=%s", webhook.id)
    return view_of(webhook)


def remove(access: WebhookAccess, webhook_id: int) -> None:
    """Delete a webhook: its link stops working, and its pipeline has none until the
    chat makes a new one."""
    webhook = repository.get_owned(access.session, access.user, webhook_id)
    repository.delete(access.session, webhook)
    logger.info("webhook.deleted webhook_id=%s", webhook_id)


def link_of(access: WebhookAccess, webhook_id: int) -> WebhookLink:
    """A webhook of the user's with its token, which only its owner may read."""
    webhook = repository.get_owned(access.session, access.user, webhook_id)
    return WebhookLink(view_of(webhook), access.box.open(webhook.token_encrypted))

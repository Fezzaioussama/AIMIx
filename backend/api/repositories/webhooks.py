"""Data access for webhooks. A webhook is found by its owner (the chat, the API) or,
when another app calls it, by the hash of its token alone."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.exceptions import NotFound
from api.models import Pipeline, User, Webhook


def for_user(session: Session, user: User) -> list[Webhook]:
    """The user's webhooks, oldest first."""
    query = select(Webhook).where(Webhook.user_id == user.id).order_by(Webhook.id)
    return list(session.scalars(query))


def get_owned(session: Session, user: User, webhook_id: int) -> Webhook:
    """A webhook of ``user``'s, or NotFound (another user's looks the same)."""
    query = select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    webhook = session.scalar(query)
    if webhook is None:
        raise NotFound(f"Webhook {webhook_id} was not found.")
    return webhook


def of_pipeline(session: Session, pipeline: Pipeline) -> Webhook | None:
    return session.scalar(select(Webhook).where(Webhook.pipeline_id == pipeline.id))


def by_token_hash(session: Session, token_hash: str) -> Webhook | None:
    return session.scalar(select(Webhook).where(Webhook.token_hash == token_hash))


def create(session: Session, pipeline: Pipeline, token_hash: str, token_encrypted: str) -> Webhook:
    """A new webhook for ``pipeline``, on, owned by the pipeline's owner."""
    webhook = Webhook(
        user_id=pipeline.user_id,
        pipeline=pipeline,
        token_hash=token_hash,
        token_encrypted=token_encrypted,
    )
    session.add(webhook)
    session.commit()
    return webhook


def set_token(session: Session, webhook: Webhook, token_hash: str, token_encrypted: str) -> None:
    """Replace the webhook's token: its old link stops working at once."""
    webhook.token_hash = token_hash
    webhook.token_encrypted = token_encrypted
    session.commit()


def set_enabled(session: Session, webhook: Webhook, enabled: bool) -> None:
    webhook.enabled = enabled
    session.commit()


def delete(session: Session, webhook: Webhook) -> None:
    session.delete(webhook)
    session.commit()


def record_call(session: Session, webhook: Webhook, at: datetime, error: str) -> None:
    """When the webhook was last called, and why that call started no run ("" if it did)."""
    webhook.last_called_at = at
    webhook.last_error = error
    session.commit()

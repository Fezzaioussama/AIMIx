"""Data access for result deliveries: by their owner, or by the pipeline a run ended in."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.exceptions import NotFound
from api.models import Delivery, Pipeline, User


@dataclass(frozen=True)
class AddressFields:
    """A new address: sealed, with its host, last characters and kind for its owner."""

    url_encrypted: str
    host: str
    hint: str
    kind: str


def for_user(session: Session, user: User) -> list[Delivery]:
    """The user's deliveries, oldest first."""
    query = select(Delivery).where(Delivery.user_id == user.id).order_by(Delivery.id)
    return list(session.scalars(query))


def get_owned(session: Session, user: User, delivery_id: int) -> Delivery:
    """A delivery of ``user``'s, or NotFound (another user's looks the same)."""
    query = select(Delivery).where(Delivery.id == delivery_id, Delivery.user_id == user.id)
    delivery = session.scalar(query)
    if delivery is None:
        raise NotFound(f"Delivery {delivery_id} was not found.")
    return delivery


def of_pipeline_id(session: Session, pipeline_id: int) -> Delivery | None:
    return session.scalar(select(Delivery).where(Delivery.pipeline_id == pipeline_id))


def set_address(session: Session, pipeline: Pipeline, fields: AddressFields) -> Delivery:
    """Send ``pipeline``'s results to a new address, which waits for its owner's
    confirmation like any new one; its first delivery is made if it has none."""
    delivery = of_pipeline_id(session, pipeline.id)
    if delivery is None:
        delivery = Delivery(user_id=pipeline.user_id, pipeline=pipeline)
        session.add(delivery)
    delivery.url_encrypted = fields.url_encrypted
    delivery.host = fields.host
    delivery.hint = fields.hint
    delivery.kind = fields.kind
    delivery.confirmed = False
    delivery.enabled = True
    delivery.last_error = ""
    session.commit()
    return delivery


def confirm(session: Session, delivery: Delivery) -> None:
    delivery.confirmed = True
    delivery.last_error = ""
    session.commit()


def set_enabled(session: Session, delivery: Delivery, enabled: bool) -> None:
    delivery.enabled = enabled
    session.commit()


def delete(session: Session, delivery: Delivery) -> None:
    session.delete(delivery)
    session.commit()


def record_send(session: Session, delivery_id: int, at: datetime, error: str) -> None:
    """When a run's result was last sent, and why it failed ("" if it was delivered)."""
    session.execute(
        update(Delivery).where(Delivery.id == delivery_id).values(last_sent_at=at, last_error=error)
    )
    session.commit()

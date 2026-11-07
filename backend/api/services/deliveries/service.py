"""A person's result deliveries: send a pipeline's results to an address (by chat), and
confirm, switch off or cancel it (the chat's card, by their own click).

An address set by chat is never confirmed: nothing is sent until its owner clicks
Confirm on screen, which posts a first message there. A page the assistant read can
therefore never send their results away (AGENTS.md §6)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from anyio import to_thread
from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import EMAIL_MAX_LENGTH, INTEGRATION_URL_MAX_LENGTH, Delivery, User
from api.repositories import deliveries as repository
from api.repositories import pipelines as pipeline_repository
from api.schemas.auth import EMAIL_PATTERN
from api.security import SecretBox
from api.services.deliveries.formats import KINDS, MAILTO, RunMessage, body_for, kind_of
from api.services.deliveries.sender import Outgoing, SendPolicy, deliver

logger = logging.getLogger(__name__)

#: How many characters of an address's end its owner is shown, to tell it apart.
HINT_LENGTH = 4
EMAIL = re.compile(EMAIL_PATTERN)


@dataclass(frozen=True)
class DeliveryAccess:
    """The signed-in user's deliveries, and the box their addresses are sealed in."""

    session: Session
    user: User
    box: SecretBox


@dataclass(frozen=True)
class DeliveryView:
    """A delivery as its owner sees it: the address's host and last characters only."""

    id: int
    pipeline_id: int
    pipeline_name: str
    destination: str
    hint: str
    service: str
    confirmed: bool
    enabled: bool
    last_sent_at: datetime | None
    last_error: str


def view_of(delivery: Delivery) -> DeliveryView:
    return DeliveryView(
        id=delivery.id,
        pipeline_id=delivery.pipeline_id,
        pipeline_name=delivery.pipeline.name,
        destination=delivery.host,
        hint=delivery.hint,
        service=KINDS[delivery.kind].label,
        confirmed=delivery.confirmed,
        enabled=delivery.enabled,
        last_sent_at=delivery.last_sent_at,
        last_error=delivery.last_error,
    )


def checked_address(url: str) -> str:
    """``url`` when it is a full https address with no credentials in it, or an email
    address (plain, or as ``mailto:``), kept as ``mailto:<address>``."""
    address = url.strip()
    email = address.removeprefix(MAILTO)
    # A link with sign-in details before its host is not an address to write to.
    if EMAIL.match(email) and not set("/:") & set(email):
        if len(email) > EMAIL_MAX_LENGTH:
            raise ValidationFailed(f"An email address holds at most {EMAIL_MAX_LENGTH} characters.")
        return f"{MAILTO}{email}"
    parts = urlsplit(address)
    if parts.scheme != "https" or not parts.hostname:
        raise ValidationFailed(
            "Give an email address, or a full address that starts with https, such as a "
            "Slack or Discord link."
        )
    if parts.username or parts.password:
        raise ValidationFailed("The address must not hold a user name or a password.")
    if len(address) > INTEGRATION_URL_MAX_LENGTH:
        raise ValidationFailed(f"An address holds at most {INTEGRATION_URL_MAX_LENGTH} characters.")
    return address


def destination_of(address: str) -> str:
    """What its owner is shown of an address: its host, or an email's domain."""
    host = urlsplit(address).hostname or address.rpartition("@")[2]
    return host.lower()


def set_address(access: DeliveryAccess, pipeline_id: int, url: str) -> DeliveryView:
    """Send the pipeline's results to ``url`` once its owner confirms it; a new address
    replaces the old one and waits for its own confirmation."""
    address = checked_address(url)
    pipeline = pipeline_repository.get_owned(access.session, access.user, pipeline_id)
    fields = repository.AddressFields(
        url_encrypted=access.box.seal(address),
        host=destination_of(address),
        hint=address[-HINT_LENGTH:],
        kind=kind_of(address),
    )
    delivery = repository.set_address(access.session, pipeline, fields)
    logger.info("delivery.address_set delivery_id=%s kind=%s", delivery.id, fields.kind)
    return view_of(delivery)


def views(access: DeliveryAccess) -> list[DeliveryView]:
    return [view_of(item) for item in repository.for_user(access.session, access.user)]


def view(access: DeliveryAccess, delivery_id: int) -> DeliveryView:
    return view_of(repository.get_owned(access.session, access.user, delivery_id))


def set_enabled(access: DeliveryAccess, delivery_id: int, enabled: bool) -> DeliveryView:
    """Stop sending results, or send them again to the address its owner confirmed."""
    delivery = repository.get_owned(access.session, access.user, delivery_id)
    repository.set_enabled(access.session, delivery, enabled)
    return view_of(delivery)


def remove(access: DeliveryAccess, delivery_id: int) -> None:
    """Cancel a delivery: its pipeline's results are no longer sent anywhere."""
    delivery = repository.get_owned(access.session, access.user, delivery_id)
    repository.delete(access.session, delivery)


def _hello(access: DeliveryAccess, delivery_id: int) -> tuple[str, str, RunMessage]:
    delivery = repository.get_owned(access.session, access.user, delivery_id)
    message = RunMessage(delivery.pipeline.name, "ready", "")
    return access.box.open(delivery.url_encrypted), delivery.kind, message


def _confirmed(access: DeliveryAccess, delivery_id: int) -> DeliveryView:
    delivery = repository.get_owned(access.session, access.user, delivery_id)
    repository.confirm(access.session, delivery)
    logger.info("delivery.confirmed delivery_id=%s", delivery.id)
    return view_of(delivery)


async def confirm(access: DeliveryAccess, delivery_id: int, policy: SendPolicy) -> DeliveryView:
    """Its owner's click: post a first message to the address and, once it is accepted
    (else ``DeliveryFailed``), send every run's result there."""
    url, kind, hello = await to_thread.run_sync(_hello, access, delivery_id)
    await deliver(policy, kind, Outgoing(url, body_for(kind, hello, policy.max_chars)))
    return await to_thread.run_sync(_confirmed, access, delivery_id)

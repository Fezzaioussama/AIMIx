"""Posting a run's result to a delivery's address: through the guarded outbound client
(public addresses only, a bounded answer, no redirect), within DELIVERY_TIMEOUT_SECONDS
and without retry. A failure is kept as the delivery's ``last_error``, never the run's."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from api.db import Database
from api.exceptions import DeliveryFailed
from api.models import RunStatus
from api.repositories import deliveries as repository
from api.repositories import runs as run_repository
from api.security import SecretBox, UnreadableSecret
from api.services.addresses import AddressNotAllowed
from api.services.deliveries.formats import RunMessage, body_for
from api.services.outbound import OutboundPolicy, guarded_client, guarded_transport
from api.services.run_recorder import utcnow
from config.settings import Settings

logger = logging.getLogger(__name__)

#: How much of an address's answer is read; nothing in it is used.
ANSWER_MAX_BYTES = 64 * 1024
#: The ends a run's result is sent on; a stopped or interrupted run sends nothing.
SENT_ON = (RunStatus.SUCCEEDED, RunStatus.FAILED)
#: Why nothing was sent when SECRET_KEY changed without its old key as a fallback.
UNREADABLE_ADDRESS = "The address can no longer be read: give it again in the chat."


def _guarded() -> httpx.AsyncBaseTransport:
    return guarded_transport(OutboundPolicy(max_response_bytes=ANSWER_MAX_BYTES))


@dataclass(frozen=True)
class SendPolicy:
    """How a delivery is sent (DELIVERY_TIMEOUT_SECONDS, DELIVERY_MAX_CHARS)."""

    timeout_seconds: float
    #: How much of a result a JSON delivery carries; chat services have their own bound.
    max_chars: int
    #: Opens the connections: the guarded transport, unless a test passes another.
    transport: Callable[[], httpx.AsyncBaseTransport] = _guarded


def send_policy(settings: Settings) -> SendPolicy:
    return SendPolicy(settings.delivery_timeout_seconds, settings.delivery_max_chars)


async def post(policy: SendPolicy, url: str, body: dict[str, Any]) -> None:
    """Post ``body`` to ``url``; ``DeliveryFailed`` says why it was not accepted."""
    host = urlsplit(url).hostname or "The address"
    try:
        async with guarded_client(
            policy.transport(), timeout=policy.timeout_seconds, follow_redirects=False
        ) as client:
            response = await client.post(url, json=body)
    except AddressNotAllowed as cause:
        raise DeliveryFailed(f"{host} is not a public address.") from cause
    except httpx.HTTPError as cause:
        raise DeliveryFailed(f"{host} could not be reached ({type(cause).__name__}).") from cause
    if not response.is_success:
        raise DeliveryFailed(f"{host} answered {response.status_code}.")


@dataclass(frozen=True)
class _Pending:
    delivery_id: int
    url: str
    kind: str
    message: RunMessage


class ResultDeliveries:
    """Sends an ended run's result where its pipeline's confirmed delivery says
    (``RunPolicy.deliveries``, called by ``RunService`` once a run has ended)."""

    def __init__(self, box: SecretBox, policy: SendPolicy) -> None:
        self._box = box
        self._policy = policy

    async def send(self, database: Database, run_id: int) -> None:
        """Post the run's result, if its pipeline has a delivery that is confirmed and
        on; a failure is logged and kept on the delivery, never raised."""
        pending = self._pending(database, run_id)
        if pending is None:
            return
        body = body_for(pending.kind, pending.message, self._policy.max_chars)
        try:
            await post(self._policy, pending.url, body)
            error = ""
        except DeliveryFailed as cause:
            error = cause.detail
        with database.session() as session:
            repository.record_send(session, pending.delivery_id, utcnow(), error)
        logger.info(
            "delivery.sent delivery_id=%s run_id=%s delivered=%s",
            pending.delivery_id,
            run_id,
            not error,
        )

    def _pending(self, database: Database, run_id: int) -> _Pending | None:
        with database.session() as session:
            run = run_repository.load(session, run_id)
            if run is None or run.pipeline_id is None or run.status not in SENT_ON:
                return None
            delivery = repository.of_pipeline_id(session, run.pipeline_id)
            if delivery is None or not (delivery.confirmed and delivery.enabled):
                return None
            try:
                url = self._box.open(delivery.url_encrypted)
            except UnreadableSecret:
                repository.record_send(session, delivery.id, utcnow(), UNREADABLE_ADDRESS)
                return None
            text = run.final_output if run.status == RunStatus.SUCCEEDED else run.error_detail
            message = RunMessage(run.pipeline_name, run.status.value, text, run.id)
            return _Pending(delivery.id, url, delivery.kind, message)

"""Sending a run's result to a delivery's address: posted through the guarded outbound
client (public addresses only, a bounded answer, no redirect), or emailed with the
files the run saved (``attachments``), each within DELIVERY_TIMEOUT_SECONDS and without
retry. A failure is kept as the delivery's ``last_error``, never the run's."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
from anyio import to_thread

from api.db import Database
from api.exceptions import DeliveryFailed, EmailNotConfigured, EmailNotSent
from api.models import Run, RunStatus
from api.repositories import deliveries as repository
from api.repositories import runs as run_repository
from api.security import SecretBox, UnreadableSecret
from api.services.addresses import AddressNotAllowed
from api.services.deliveries.attachments import RunWindow, saved_during
from api.services.deliveries.formats import MAILTO, RunMessage, body_for
from api.services.email import Attachment, Email, EmailSender, NullSender, email_sender
from api.services.files.storage import WorkspaceStorage
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
    """How a delivery is sent (DELIVERY_TIMEOUT_SECONDS, DELIVERY_MAX_CHARS, the email
    sender and DELIVERY_EMAIL_MAX_ATTACHMENT_BYTES)."""

    timeout_seconds: float
    #: How much of a result a JSON or email delivery carries; chat services have their own bound.
    max_chars: int
    #: Opens the connections: the guarded transport, unless a test passes another.
    transport: Callable[[], httpx.AsyncBaseTransport] = _guarded
    #: Sends an email delivery (SMTP_*); the null sender refuses while none is configured.
    email: EmailSender = field(default_factory=NullSender)
    #: The most the run's files may add to one email, in bytes; 0 attaches none.
    attachment_max_bytes: int = 0


def send_policy(settings: Settings) -> SendPolicy:
    return SendPolicy(
        settings.delivery_timeout_seconds,
        settings.delivery_max_chars,
        email=email_sender(settings),
        attachment_max_bytes=settings.delivery_email_max_attachment_bytes,
    )


@dataclass(frozen=True)
class Outgoing:
    """One message to deliver: where, what, and (an email) the run's files."""

    url: str
    body: dict[str, Any]
    attachments: tuple[Attachment, ...] = ()


async def post(policy: SendPolicy, outgoing: Outgoing) -> None:
    """Post the body to the address; ``DeliveryFailed`` says why it was not accepted."""
    host = urlsplit(outgoing.url).hostname or "The address"
    try:
        async with guarded_client(
            policy.transport(), timeout=policy.timeout_seconds, follow_redirects=False
        ) as client:
            response = await client.post(outgoing.url, json=outgoing.body)
    except AddressNotAllowed as cause:
        raise DeliveryFailed(f"{host} is not a public address.") from cause
    except httpx.HTTPError as cause:
        raise DeliveryFailed(f"{host} could not be reached ({type(cause).__name__}).") from cause
    if not response.is_success:
        raise DeliveryFailed(f"{host} answered {response.status_code}.")


async def send_email(policy: SendPolicy, outgoing: Outgoing) -> None:
    """Email the body (its subject and text) to the ``mailto:`` address, with the run's
    files attached; ``DeliveryFailed`` says why it was not sent."""
    to = outgoing.url.removeprefix(MAILTO)
    subject, text = str(outgoing.body["subject"]), str(outgoing.body["text"])
    email = Email(to, subject, text, outgoing.attachments)
    try:
        await to_thread.run_sync(policy.email.send, email)
    except (EmailNotConfigured, EmailNotSent) as cause:
        raise DeliveryFailed(cause.detail) from cause


Transport = Callable[[SendPolicy, Outgoing], Awaitable[None]]

#: How each kind of address is reached; any kind not listed is posted to (Strategy +
#: Registry, §5 O). An email carries the files the run saved.
TRANSPORTS: dict[str, Transport] = {"email": send_email}
ATTACHES_FILES = frozenset(TRANSPORTS)


async def deliver(policy: SendPolicy, kind: str, outgoing: Outgoing) -> None:
    """Send ``outgoing`` the way addresses of ``kind`` are reached."""
    await TRANSPORTS.get(kind, post)(policy, outgoing)


@dataclass(frozen=True)
class _Pending:
    delivery_id: int
    url: str
    kind: str
    message: RunMessage
    attachments: tuple[Attachment, ...] = ()


#: The owner's workspace, by user id: where a run's files are read for an email.
Workspaces = Callable[[int], WorkspaceStorage]


class ResultDeliveries:
    """Sends an ended run's result where its pipeline's confirmed delivery says
    (``RunPolicy.deliveries``, called by ``RunService`` once a run has ended)."""

    def __init__(
        self, box: SecretBox, policy: SendPolicy, workspaces: Workspaces | None = None
    ) -> None:
        self._box = box
        self._policy = policy
        #: None attaches no file to an email (tests, and a policy without workspaces).
        self._workspaces = workspaces

    async def send(self, database: Database, run_id: int) -> None:
        """Send the run's result, if its pipeline has a delivery that is confirmed and
        on; a failure is logged and kept on the delivery, never raised."""
        pending = self._pending(database, run_id)
        if pending is None:
            return
        body = body_for(pending.kind, pending.message, self._policy.max_chars)
        outgoing = Outgoing(pending.url, body, pending.attachments)
        try:
            await deliver(self._policy, pending.kind, outgoing)
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
            files = self._attachments(run, delivery.kind)
            return _Pending(delivery.id, url, delivery.kind, message, files)

    def _attachments(self, run: Run, kind: str) -> tuple[Attachment, ...]:
        """The files saved during the run, for a kind of address that carries them."""
        if kind not in ATTACHES_FILES or self._workspaces is None or run.started_at is None:
            return ()
        window = RunWindow(run.started_at, run.finished_at)
        files = saved_during(
            self._workspaces(run.user_id), window, self._policy.attachment_max_bytes
        )
        logger.info("delivery.attachments run_id=%s files=%d", run.id, len(files))
        return files

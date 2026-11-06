"""Emails that tell an account what happened while nobody was looking: a run ended,
a run waits for its owner's answer, a schedule could not start.

Sent to the account's address while its notifications are on. A failure is logged
and never raised: a run's end, a request, a schedule's error are recorded whether
or not the email leaves. The texts are pure functions; ``Notifier`` reads what they
need and sends. Addresses are never logged (§6).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from api.db import Database
from api.exceptions import EmailNotConfigured, EmailNotSent
from api.models import Run, RunStatus, User
from api.repositories import runs, users
from api.repositories import schedules as schedule_repository
from api.services.email import Email, EmailSender, email_sender
from config.settings import Settings

logger = logging.getLogger(__name__)

#: The ends a run's owner is told about; a stopped or interrupted run says nothing.
ENDED = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED})
SIGNATURE = "\n— AIMIx\n"


@dataclass(frozen=True)
class NotificationLinks:
    """Where the emails send people: the app's public address (§7 Value Object)."""

    public_url: str

    def run(self, run_id: int) -> str:
        return f"{self.public_url}/runs/{run_id}"

    def schedules(self) -> str:
        return f"{self.public_url}/schedules"


def excerpt(text: str, max_chars: int) -> str:
    """The start of a result, cut at ``max_chars`` with a note; "" for nothing."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}…\n\n(The rest is on the run's page.)"


def run_ended_email(to: str, run: Run, link: str, max_chars: int) -> Email:
    """Pure: the message about a run that finished or failed."""
    if run.status == RunStatus.SUCCEEDED:
        subject = f'"{run.pipeline_name}" finished'
        body = f'Your run of "{run.pipeline_name}" finished.\n\nOpen it: {link}'
        result = excerpt(run.final_output, max_chars)
        if result:
            body += f"\n\n{result}"
    else:
        subject = f'"{run.pipeline_name}" failed'
        body = (
            f'Your run of "{run.pipeline_name}" failed: {run.error_detail}\n\n'
            f"The steps that finished are kept, and Resume continues it: {link}"
        )
    return Email(to, subject, f"{body}\n{SIGNATURE}")


def run_waiting_email(to: str, run: Run, link: str) -> Email:
    """Pure: the message about a run whose agent asked before acting."""
    body = (
        f'An agent of your run of "{run.pipeline_name}" asks for your approval before '
        f"it acts. The run waits for your answer (for a while, then goes on without "
        f"it).\n\nApprove or decline: {link}"
    )
    return Email(to, f'"{run.pipeline_name}" is waiting for you', f"{body}\n{SIGNATURE}")


def schedule_failed_email(to: str, pipeline_name: str, error: str, link: str) -> Email:
    """Pure: the message about a scheduled run that could not start."""
    body = (
        f'The scheduled run of "{pipeline_name}" could not start: {error}\n\n'
        f"The schedule keeps its next time. Check it: {link}"
    )
    return Email(to, f'"{pipeline_name}" could not run as scheduled', f"{body}\n{SIGNATURE}")


class Notifier:
    """Sends each kind of notification to the account it concerns, when it has an
    address and wants them."""

    def __init__(
        self, sender: EmailSender, links: NotificationLinks, result_max_chars: int
    ) -> None:
        self._sender = sender
        self._links = links
        self._result_max_chars = result_max_chars

    def run_ended(self, database: Database, run_id: int) -> bool:
        """Tell the owner that the run finished or failed; True when the email left."""
        with database.session() as session:
            run = runs.load(session, run_id)
            if run is None or run.status not in ENDED:
                return False
            owner = users.get(session, run.user_id)
        link = self._links.run(run_id)
        make = lambda to: run_ended_email(to, run, link, self._result_max_chars)  # noqa: E731
        return self._send(owner, make, "run_ended", run_id)

    def run_waiting(self, database: Database, run_id: int) -> bool:
        """Tell the owner that the run waits for their answer; True when the email left."""
        with database.session() as session:
            run = runs.load(session, run_id)
            if run is None:
                return False
            owner = users.get(session, run.user_id)
        link = self._links.run(run_id)
        return self._send(owner, lambda to: run_waiting_email(to, run, link), "run_waiting", run_id)

    def schedule_failed(self, database: Database, schedule_id: int, error: str) -> bool:
        """Tell the owner why a scheduled run could not start; True when the email left."""
        with database.session() as session:
            schedule = schedule_repository.get(session, schedule_id)
            if schedule is None:
                return False
            name = schedule.pipeline.name
            owner = users.get(session, schedule.user_id)
        link = self._links.schedules()
        make = lambda to: schedule_failed_email(to, name, error, link)  # noqa: E731
        return self._send(owner, make, "schedule_failed", schedule_id)

    def _send(
        self, owner: User | None, make: Callable[[str], Email], kind: str, about: int
    ) -> bool:
        if owner is None or not owner.email or not owner.email_notifications:
            return False
        try:
            self._sender.send(make(owner.email))
        except EmailNotConfigured:
            logger.info("notification.skipped kind=%s id=%s reason=no_smtp", kind, about)
            return False
        except EmailNotSent as error:
            logger.warning(
                "notification.not_sent kind=%s id=%s user_id=%s detail=%s",
                kind,
                about,
                owner.id,
                error.detail,
            )
            return False
        logger.info("notification.sent kind=%s id=%s user_id=%s", kind, about, owner.id)
        return True


def notifier(settings: Settings) -> Notifier:
    """The app's notifier: the configured sender and the app's public address."""
    return Notifier(
        email_sender(settings),
        NotificationLinks(settings.app_public_url),
        settings.notification_result_max_chars,
    )

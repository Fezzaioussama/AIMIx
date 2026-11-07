"""The files a run saved, attached to the email that carries its result: those written
to the owner's workspace between the run's start and end (with a little slack, as the
files' times are the disk's), newest first, as many as fit together within
DELIVERY_EMAIL_MAX_ATTACHMENT_BYTES. Reads files only; no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from api.services.email import Attachment
from api.services.files.names import media_type
from api.services.files.service import entries
from api.services.files.storage import WorkspaceStorage
from api.services.run_recorder import utcnow

#: Seconds either side of the run's start and end a file's time may fall in.
SLACK_SECONDS = 2.0


def _as_utc(moment: datetime) -> datetime:
    # SQLite hands back the UTC time it stored without its zone.
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class RunWindow:
    """When a run worked: its start, and its end (None while it has not ended)."""

    started_at: datetime
    finished_at: datetime | None

    def holds(self, moment: datetime) -> bool:
        slack = timedelta(seconds=SLACK_SECONDS)
        end = _as_utc(self.finished_at) if self.finished_at else utcnow()
        return _as_utc(self.started_at) - slack <= _as_utc(moment) <= end + slack


def saved_during(
    storage: WorkspaceStorage, window: RunWindow, max_bytes: int
) -> tuple[Attachment, ...]:
    """The files saved in ``window``, newest first, while they fit in ``max_bytes``
    together; a file too big for the room left is skipped, not the rest."""
    if max_bytes <= 0:
        return ()
    chosen: list[Attachment] = []
    room = max_bytes
    for entry in entries(storage):
        if not window.holds(entry.modified_at) or entry.size > room:
            continue
        path = storage.existing(entry.path)
        chosen.append(Attachment(path.name, path.read_bytes(), media_type(path.name)))
        room -= entry.size
    return tuple(chosen)

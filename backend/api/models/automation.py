"""What starts a pipeline's runs without its owner, and where their results go: schedules,
webhooks other apps call, and result deliveries."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import (
    HOST_MAX_LENGTH,
    STATUS_MAX_LENGTH,
    TIMEZONE_MAX_LENGTH,
    TOKEN_HASH_LENGTH,
    Base,
    _status_type,
    _utcnow,
)
from api.models.pipelines import Pipeline


class ScheduleFrequency(str, Enum):
    """How often a schedule runs; hourly is the most often. What each preset
    means is in ``services/schedules/timing.FREQUENCIES``."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Schedule(Base):
    """Starts runs of one of its owner's pipelines on its own, at a preset frequency.

    ``hour`` and ``minute`` are a wall-clock time in ``timezone`` (an IANA
    name), so a schedule keeps its local time across daylight-saving changes;
    an hourly one uses the minute only. ``weekday`` (0 = Monday) is set for a
    weekly schedule and ``day_of_month`` (1-31) for a monthly one.
    ``input_text`` / ``input_values`` are what every run is started with, and
    ``max_cost_usd`` / ``max_tokens`` its limits (None: the server's default).
    ``next_run_at`` (UTC) is None while the schedule is off. ``last_error``
    says why its latest occurrence could not start; "" means it started.
    ``claimed_occurrence`` is the occurrence a tick claimed and has not settled
    yet (its run not saved, not passed over, not failed), so a restart can
    start the one a process died on; None otherwise.
    Deleting the pipeline deletes its schedules; their runs stay.
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pipeline_id: Mapped[int] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), index=True
    )
    frequency: Mapped[ScheduleFrequency] = mapped_column(_status_type(ScheduleFrequency))
    hour: Mapped[int] = mapped_column(default=0)
    minute: Mapped[int] = mapped_column(default=0)
    weekday: Mapped[int | None]
    day_of_month: Mapped[int | None]
    timezone: Mapped[str] = mapped_column(String(TIMEZONE_MAX_LENGTH))
    input_text: Mapped[str] = mapped_column(Text, default="")
    input_values: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    max_cost_usd: Mapped[float | None]
    max_tokens: Mapped[int | None]
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(index=True)
    claimed_occurrence: Mapped[datetime | None]
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    pipeline: Mapped[Pipeline] = relationship()


class Webhook(Base):
    """A secret link another app calls to start a run of one of its owner's pipelines.

    Its token is kept twice: ``token_hash`` (SHA-256) finds the webhook when it is
    called, and ``token_encrypted`` (the server's secret box) lets its owner read the
    link again. One per pipeline; deleting the pipeline deletes it. ``last_error``
    says why its latest call started no run; "" means it started one.
    """

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pipeline_id: Mapped[int] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), unique=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    token_encrypted: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_called_at: Mapped[datetime | None]
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    pipeline: Mapped[Pipeline] = relationship()


class Delivery(Base):
    """Where a pipeline's results are posted when one of its runs ends: a Slack,
    Discord or any other webhook address, sealed by the server's secret box.

    Set by chat, it sends nothing until its owner confirms it on screen
    (``confirmed``), so a page the assistant read cannot send their results away. One
    per pipeline; deleting the pipeline deletes it. ``kind`` is a key of
    ``deliveries.formats.KINDS``; ``last_error`` says why the latest sending failed.
    """

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pipeline_id: Mapped[int] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), unique=True
    )
    url_encrypted: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(HOST_MAX_LENGTH))
    hint: Mapped[str] = mapped_column(String(STATUS_MAX_LENGTH))
    kind: Mapped[str] = mapped_column(String(STATUS_MAX_LENGTH))
    confirmed: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_sent_at: Mapped[datetime | None]
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    pipeline: Mapped[Pipeline] = relationship()

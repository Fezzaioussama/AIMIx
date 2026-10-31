"""Everything an account holds, at once: a copy of it, and its deletion (the
rights of access, portability and erasure, GDPR art. 15, 17 and 20).

The copy is what the API shows of each thing, so it never holds a secret: saved
API keys and integration header values stay sealed, only their hints are in it.
Deleting removes the files first, then every row the account owns, so a
failure leaves the account in place to try again, never a half-deleted one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from api.exceptions import Conflict, ExportTooLarge
from api.models import Integration, Pipeline, ProviderSetting, Run, RunApproval, Schedule, User
from api.repositories import (
    active_runs,
    approvals,
    integrations,
    pipelines,
    provider_settings,
    runs,
    schedules,
    stored_size,
    users,
)
from api.services import accounts
from api.services.files import service as file_service
from api.services.files.service import FileEntry
from api.services.files.storage import WorkspaceStorage, user_workspace_dir
from config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportOptions:
    #: The moment the copy is of.
    now: datetime
    #: Characters of stored text past which no copy is made (ACCOUNT_EXPORT_MAX_CHARS),
    #: since it is built in memory; None for the operator's command.
    max_chars: int | None = None


@dataclass(frozen=True)
class AccountExport:
    """What one account holds, as of ``exported_at`` (§7 DTO)."""

    exported_at: datetime
    account: User
    provider_settings: list[ProviderSetting]
    pipelines: list[Pipeline]
    runs: list[Run]
    #: Every tool call a run asked its owner about, answered or not.
    approvals: list[RunApproval]
    schedules: list[Schedule]
    integrations: list[Integration]
    files: list[FileEntry]


def workspace_of(settings: Settings, user_id: int) -> WorkspaceStorage:
    """The private directory of one account, the one its agents use too."""
    return WorkspaceStorage(
        user_workspace_dir(settings.workspace_dir, user_id),
        settings.workspace_max_total_bytes,
        settings.workspace_max_files,
        min_free_bytes=settings.workspace_min_free_bytes,
    )


def open_account(session: Session, settings: Settings, credentials: accounts.Credentials) -> User:
    """Create an account that starts with no files. SQLite gives a deleted
    account's id to the next one, so a directory left under that id (its
    removal failed, or a write raced it) is cleared before anyone can read it."""
    user = accounts.register(
        session, credentials.username, credentials.password, settings.password_hash_iterations
    )
    workspace_of(settings, user.id).remove()
    return user


def export_account(
    session: Session, user: User, files: WorkspaceStorage, options: ExportOptions
) -> AccountExport:
    """Everything the account holds; ``ExportTooLarge`` past ``options.max_chars``,
    measured in the database before anything is loaded."""
    if options.max_chars is not None and (
        stored_size.text_characters(session, user) > options.max_chars
    ):
        raise ExportTooLarge(
            "Your account holds too much to download at once. Delete runs you no longer "
            "need, or ask the operator for a full copy (see the privacy policy)."
        )
    return AccountExport(
        exported_at=options.now,
        account=user,
        provider_settings=list(provider_settings.for_user(session, user).values()),
        pipelines=pipelines.for_user(session, user),
        runs=runs.all_for_user(session, user),
        approvals=approvals.for_user(session, user),
        schedules=schedules.for_user(session, user),
        integrations=integrations.for_user(session, user),
        files=file_service.entries(files),
    )


def delete_account(session: Session, user: User, files: WorkspaceStorage) -> None:
    """Delete the account's files, then the account and every row it owns; its
    sessions end with it. Refused while one of its runs is active, since that
    run would go on writing for an account that no longer exists."""
    if session.scalar(active_runs.count_of(user.id)):
        raise Conflict("Stop your active runs before deleting your account.")
    user_id = user.id
    files.remove()
    users.delete(session, user)
    logger.info("accounts.deleted user_id=%s", user_id)

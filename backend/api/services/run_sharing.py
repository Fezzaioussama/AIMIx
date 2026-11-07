"""Sharing a run's report by secret link: anyone who has the link reads the report,
read-only, without an account. Its owner makes the link once a run has ended (the
same link again after that), reads it again, and withdraws it; the link is kept like
a webhook's (``secret_links``). What the page shows is ``schemas/runs.shared_view``:
never what the run was given, its prompts or the owner's feedback (AGENTS.md §6).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from api.exceptions import Conflict, NotFound
from api.models import ACTIVE_RUN_STATUSES, Run, RunShare, User
from api.repositories import run_shares as repository
from api.repositories import runs
from api.security import SecretBox
from api.services.secret_links import new_token, token_hash

logger = logging.getLogger(__name__)

#: Where a shared run is read in the app (``frontend/src/core/routes.ts`` mirrors it).
SHARED_RUN_PATH = "/shared"
NOT_SHARED = "This link does not show a run: it may have been withdrawn."


@dataclass(frozen=True)
class ShareAccess:
    """The signed-in user's share links, the box their tokens are sealed in, and the
    app's public address (APP_PUBLIC_URL) the links point at."""

    session: Session
    user: User
    box: SecretBox
    public_url: str


@dataclass(frozen=True)
class ShareLink:
    """A run's link, for its owner's screen only (§7 Value Object)."""

    token: str
    url: str
    created_at: datetime


def _link(access: ShareAccess, share: RunShare) -> ShareLink:
    token = access.box.open(share.token_encrypted)
    return ShareLink(token, f"{access.public_url}{SHARED_RUN_PATH}/{token}", share.created_at)


def link_of(access: ShareAccess, run_id: int) -> ShareLink | None:
    """The link of one of the user's runs, or None while it is not shared."""
    run = runs.get_owned(access.session, access.user, run_id)
    share = repository.of_run(access.session, run.id)
    return None if share is None else _link(access, share)


def share(access: ShareAccess, run_id: int) -> ShareLink:
    """A link to the run's report, made once: the same link comes back after that.
    Only a run that has ended is shared (``Conflict`` while it is active)."""
    run = runs.get_owned(access.session, access.user, run_id)
    if run.status in ACTIVE_RUN_STATUSES:
        raise Conflict("Share the run once it has ended.")
    existing = repository.of_run(access.session, run.id)
    if existing is not None:
        return _link(access, existing)
    made = new_token(access.box)
    created = repository.create(access.session, run.id, made.hash, made.sealed)
    logger.info("run.shared run_id=%s", run.id)
    return _link(access, created)


def unshare(access: ShareAccess, run_id: int) -> None:
    """Withdraw the run's link: it stops working at once. Nothing to withdraw is fine."""
    run = runs.get_owned(access.session, access.user, run_id)
    existing = repository.of_run(access.session, run.id)
    if existing is not None:
        repository.delete(access.session, existing)
        logger.info("run.unshared run_id=%s", run.id)


def shared_run(session: Session, token: str) -> Run:
    """The run a link shows; ``NotFound`` for an unknown or withdrawn link."""
    found = repository.by_token_hash(session, token_hash(token))
    run = None if found is None else runs.load(session, found.run_id)
    if run is None:
        raise NotFound(NOT_SHARED)
    return run

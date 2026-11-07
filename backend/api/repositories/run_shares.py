"""Data access for run share links (``services/run_sharing``): one per run, found by
the hash of its token alone when the link is opened (AGENTS.md §7 Repository)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import RunShare


def of_run(session: Session, run_id: int) -> RunShare | None:
    return session.scalar(select(RunShare).where(RunShare.run_id == run_id))


def by_token_hash(session: Session, token_hash: str) -> RunShare | None:
    return session.scalar(select(RunShare).where(RunShare.token_hash == token_hash))


def create(session: Session, run_id: int, token_hash: str, token_encrypted: str) -> RunShare:
    share = RunShare(run_id=run_id, token_hash=token_hash, token_encrypted=token_encrypted)
    session.add(share)
    session.commit()
    return share


def delete(session: Session, share: RunShare) -> None:
    session.delete(share)
    session.commit()

"""Bulk writes shared by the repositories that change rows compare-and-set."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult
from sqlalchemy.orm import Session


def changed(session: Session, statement: Any) -> int:
    """Execute a bulk UPDATE; how many rows it changed."""
    result = session.execute(statement, execution_options={"synchronize_session": False})
    return cast(CursorResult[Any], result).rowcount

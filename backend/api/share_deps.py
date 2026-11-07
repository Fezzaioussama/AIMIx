"""The run shares' part of ``deps.py``: the signed-in user's share links (a run's
report, read by anyone who has the link). Tests swap it through
``app.dependency_overrides`` like any other dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from api.deps import AppSettings, CurrentUser, DbSession, Secrets
from api.services.run_sharing import ShareAccess


def share_access(
    user: CurrentUser, session: DbSession, box: Secrets, settings: AppSettings
) -> ShareAccess:
    """The signed-in user's share links, pointing at APP_PUBLIC_URL."""
    return ShareAccess(session, user, box, settings.app_public_url)


Shares = Annotated[ShareAccess, Depends(share_access)]

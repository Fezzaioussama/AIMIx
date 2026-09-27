"""Small helpers for the HTTP boundary."""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request


def authenticated_user(request: Request) -> User:
    """Return the request's user, narrowed to a real account.

    ``request.user`` is typed ``User | AnonymousUser``. Endpoints guarded by
    IsAuthenticated only ever see a real user, and this makes that guarantee
    explicit instead of leaving callers to assume it.
    """
    user = request.user
    if not isinstance(user, User):
        raise NotAuthenticated("This endpoint requires an authenticated user.")
    return user

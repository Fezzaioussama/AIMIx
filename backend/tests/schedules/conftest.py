"""Fixtures of the schedules HTTP tests: a signed-in client on a clock the test sets."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import users
from api.security import hash_password
from api.services.run_recorder import utcnow
from tests.conftest import FakeProvider
from tests.schedules.support import Clock
from tests.test_endpoints import make_pipeline


@pytest.fixture
def clock(app: FastAPI) -> Clock:
    """Every request's "now" is this clock's (``Now`` resolves ``utcnow``)."""
    clock = Clock()
    app.dependency_overrides[utcnow] = clock
    return clock


@pytest.fixture
def pipeline(session: Session, user: User) -> Pipeline:
    return make_pipeline(session, user, "Digest")


@pytest.fixture
def stranger(session: Session) -> User:
    return users.create(session, "stranger", hash_password("x-pass-2891", 1))


@pytest.fixture
def api(auth_client: TestClient, clock: Clock, fake_provider: FakeProvider) -> TestClient:
    """A signed-in client on the test clock, whose pipeline agents are fake."""
    return auth_client

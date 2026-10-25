"""Database-backed throttling: atomic counting, the bucket-creation race, pruning,
and which client address a request is counted against."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from api.db import Database
from api.deps import app_settings
from api.models import Base, RateLimitBucket, User
from api.repositories.rate_limits import RateLimitAttempt, consume
from api.services.rate_limits import client_address
from tests.conftest import TEST_SETTINGS

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
LOGIN = RateLimitAttempt("client-a", "/api/login", limit=3, window_seconds=60)


@pytest.fixture
def file_database(tmp_path: Path) -> Iterator[Database]:
    """A database on disk, so several connections (threads) really share it."""
    database = Database(f"sqlite:///{tmp_path / 'limits.sqlite3'}")
    Base.metadata.create_all(database.engine)
    yield database
    database.engine.dispose()


def buckets(session: Session) -> list[tuple[str, str, int]]:
    rows = session.execute(
        select(RateLimitBucket.identity_hash, RateLimitBucket.action, RateLimitBucket.hits)
    )
    return sorted((row.identity_hash, row.action, row.hits) for row in rows)


def test_a_window_counts_up_to_its_limit_then_says_how_long_to_wait(session: Session) -> None:
    results = [consume(session, LOGIN, T0 + timedelta(seconds=n)) for n in range(4)]

    assert results[:3] == [None, None, None]
    assert results[3] == 57
    assert buckets(session) == [("client-a", "/api/login", 3)]


def test_an_ended_window_starts_again(session: Session) -> None:
    for _ in range(3):
        consume(session, LOGIN, T0)

    assert consume(session, LOGIN, T0 + timedelta(seconds=60)) is None
    assert buckets(session) == [("client-a", "/api/login", 1)]


def test_a_bucket_another_request_just_created_is_counted_not_a_server_error(
    session: Session,
) -> None:
    """Two first requests for one key both find no bucket and both insert: the
    loser's insert breaks the unique key. It must count, not fail with a 500."""
    connection = session.connection()
    raced = []

    def insert_first(_conn: Any, cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        if statement.startswith("INSERT INTO rate_limit_buckets") and not raced:
            raced.append(statement)
            cursor.execute(statement, parameters)  # the other request wins the race

    event.listen(connection.engine, "before_cursor_execute", insert_first)
    try:
        assert consume(session, LOGIN, T0) is None
    finally:
        event.remove(connection.engine, "before_cursor_execute", insert_first)

    assert raced
    assert buckets(session) == [("client-a", "/api/login", 1)]


def test_concurrent_requests_never_count_past_the_limit(file_database: Database) -> None:
    start = threading.Barrier(8)
    outcomes: list[int | Exception | None] = []

    def request() -> None:
        start.wait()
        with file_database.session() as session:
            try:
                outcomes.append(consume(session, LOGIN, T0))
            except Exception as error:  # recorded, so the assertion names it
                outcomes.append(error)

    threads = [threading.Thread(target=request) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count(None) == LOGIN.limit
    assert all(isinstance(outcome, int) for outcome in outcomes if outcome is not None)
    with file_database.session() as session:
        assert buckets(session) == [("client-a", "/api/login", LOGIN.limit)]


def test_creating_a_bucket_prunes_the_action_buckets_whose_window_ended(
    session: Session,
) -> None:
    consume(session, LOGIN, T0)
    other_action = RateLimitAttempt("client-a", "sign-in-failures", 3, 900)
    consume(session, other_action, T0)

    # A new client a window later: client-a's login window has ended.
    newcomer = RateLimitAttempt("client-b", "/api/login", 3, 60)
    consume(session, newcomer, T0 + timedelta(seconds=61))

    assert buckets(session) == [
        ("client-a", "sign-in-failures", 1),  # its 15-minute window is still running
        ("client-b", "/api/login", 1),
    ]


def test_a_running_window_is_never_pruned(session: Session) -> None:
    consume(session, LOGIN, T0)
    consume(session, RateLimitAttempt("client-b", "/api/login", 3, 60), T0 + timedelta(seconds=59))

    assert [row[0] for row in buckets(session)] == ["client-a", "client-b"]


# --- which client a request counts against -----------------------------------


@pytest.mark.parametrize(
    ("headers", "hops", "expected"),
    [
        ([], 0, "peer"),
        (["198.51.100.9"], 0, "peer"),  # no trusted proxy: the header is ignored
        ([], 2, "peer"),  # no header at all
        (["", " "], 2, "peer"),
        (["203.0.113.7, 10.1.2.3"], 2, "203.0.113.7"),  # [client, platform hop]
        (["198.51.100.9, 203.0.113.7, 10.1.2.3"], 2, "203.0.113.7"),  # spoofed entry
        (["6.6.6.6", "203.0.113.7, 10.1.2.3"], 2, "203.0.113.7"),  # header repeated
        (["203.0.113.7"], 2, "203.0.113.7"),  # shorter than hops: leftmost
        (["203.0.113.7, 10.1.2.3"], 3, "203.0.113.7"),
        (["198.51.100.9, 203.0.113.7"], 1, "203.0.113.7"),
        (["203.0.113.7:51234"], 1, "203.0.113.7"),  # a port is not part of the client
        (["[2001:db8::1]:51234"], 1, "2001:db8::1"),
        (["2001:db8::1"], 1, "2001:db8::1"),
    ],
)
def test_the_client_address_comes_from_the_trusted_proxies_only(
    headers: list[str], hops: int, expected: str
) -> None:
    assert client_address(headers, "peer", hops) == expected


def test_a_rotated_forwarded_for_does_not_reset_the_login_limit(app: FastAPI, user: User) -> None:
    """The image runs uvicorn trusting every proxy header, which hands the app
    the leftmost (client-written) entry as ``request.client``."""
    limited = TEST_SETTINGS.model_copy(
        update={"auth_rate_limit_requests": 2, "trusted_proxy_hops": 1}
    )
    app.dependency_overrides[app_settings] = lambda: limited
    payload = {"username": user.username, "password": "wrong-password"}

    with TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*")) as client:
        statuses = [
            client.post(
                "/api/login", json=payload, headers={"X-Forwarded-For": f"10.0.0.{n}, 203.0.113.7"}
            ).status_code
            for n in range(3)
        ]
        other_client = client.post(
            "/api/login", json=payload, headers={"X-Forwarded-For": "203.0.113.8"}
        )

    assert statuses == [401, 401, 429]
    assert other_client.status_code == 401

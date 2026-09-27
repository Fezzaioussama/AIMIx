"""Password hashing, the password policy, and token signing."""

from __future__ import annotations

from datetime import timedelta

import pytest

from api.security import TokenSigner, hash_password, verify_password
from api.services import password_policy

#: Produced by Django 5.2's PBKDF2PasswordHasher (1,000 iterations), so this
#: checks compatibility with the previous backend, not with ourselves.
DJANGO_HASH = "pbkdf2_sha256$1000$seasaltseasalt$yVxzXa72tWS0k52beX7lX7hVqRwAzetc2Fbi6JE/Wsw="
DJANGO_PASSWORD = "lètmein-legacy-9182"


def test_a_hash_made_by_django_verifies() -> None:
    assert verify_password(DJANGO_PASSWORD, DJANGO_HASH)
    assert not verify_password("wrong", DJANGO_HASH)


def test_new_hashes_round_trip_and_are_salted() -> None:
    first, second = hash_password("secret-pass", 10), hash_password("secret-pass", 10)
    assert first != second
    assert first.startswith("pbkdf2_sha256$10$")
    assert verify_password("secret-pass", first)


@pytest.mark.parametrize("encoded", ["", "md5$1$salt$x", "pbkdf2_sha256$zero$salt$x"])
def test_unreadable_hashes_never_verify(encoded: str) -> None:
    assert not verify_password("anything", encoded)


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("short1", "too short"),
        ("12345678901", "entirely numeric"),
        ("password123", "too common"),
        ("tester123", "too similar"),
    ],
)
def test_the_password_policy_matches_the_django_rules(password: str, problem: str) -> None:
    assert any(problem in message for message in password_policy.problems(password, "tester"))


def test_a_good_password_passes() -> None:
    assert password_policy.problems("a-strong-pass-9182", "newcomer") == []


KEY = "k" * 32
SIGNER = TokenSigner(KEY, timedelta(minutes=5), timedelta(days=1))


def test_tokens_carry_the_user_and_their_type() -> None:
    access = SIGNER.issue(7, "access")
    assert SIGNER.user_id(access, "access") == 7
    assert SIGNER.user_id(access, "refresh") is None


def test_expired_and_foreign_tokens_are_rejected() -> None:
    expired = TokenSigner(KEY, timedelta(seconds=-1), timedelta(days=1)).issue(7, "access")
    foreign = TokenSigner("o" * 32, timedelta(minutes=5), timedelta(days=1)).issue(7, "access")
    assert SIGNER.user_id(expired, "access") is None
    assert SIGNER.user_id(foreign, "access") is None

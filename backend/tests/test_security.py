"""Password hashing, the password policy, token signing and credential encryption."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from api.deps import token_signer
from api.security import (
    JWT_ALGORITHM,
    SecretBox,
    TokenSigner,
    TokenSubject,
    UnreadableSecret,
    hash_iterations,
    hash_password,
    secret_box_for,
    verify_password,
)
from api.services import password_policy
from tests.conftest import TEST_SETTINGS

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


def test_a_new_password_needs_twelve_characters_of_any_kind() -> None:
    assert any("too short" in m for m in password_policy.problems("plum-violin", "newcomer"))
    assert password_policy.problems("plumviolinoak", "newcomer") == []


KEY = "k" * 32
MINUTE = timedelta(minutes=1)
SIGNER = TokenSigner(KEY, timedelta(minutes=5), timedelta(days=1))


def test_tokens_carry_the_user_and_their_type() -> None:
    access = SIGNER.issue(7, "access")
    assert SIGNER.user_id(access, "access") == 7
    assert SIGNER.user_id(access, "refresh") is None


def test_tokens_carry_the_account_token_version() -> None:
    assert SIGNER.subject(SIGNER.issue(7, "access", 3), "access") == TokenSubject(7, 3)
    # A token from before versions existed counts as version 0.
    unversioned = jwt.encode(
        {"token_type": "access", "user_id": 7, "exp": datetime.now(timezone.utc) + MINUTE},
        KEY,
        algorithm=JWT_ALGORITHM,
    )
    assert SIGNER.subject(unversioned, "access") == TokenSubject(7, 0)


def test_expired_and_foreign_tokens_are_rejected() -> None:
    expired = TokenSigner(KEY, timedelta(seconds=-1), timedelta(days=1)).issue(7, "access")
    foreign = TokenSigner("o" * 32, timedelta(minutes=5), timedelta(days=1)).issue(7, "access")
    assert SIGNER.user_id(expired, "access") is None
    assert SIGNER.user_id(foreign, "access") is None


def test_a_token_without_an_expiry_is_rejected() -> None:
    forever = jwt.encode({"token_type": "access", "user_id": 7}, KEY, algorithm=JWT_ALGORITHM)
    assert SIGNER.user_id(forever, "access") is None


def test_tokens_signed_with_a_previous_key_verify_during_a_rotation() -> None:
    old = TokenSigner("o" * 32, MINUTE, timedelta(days=1)).issue(7, "access")
    rotated = TokenSigner(KEY, MINUTE, timedelta(days=1), fallback_keys=("o" * 32,))

    assert rotated.user_id(old, "access") == 7
    assert SIGNER.user_id(old, "access") is None  # without the fallback it is foreign
    # New tokens are signed with the current key only.
    assert SIGNER.user_id(rotated.issue(8, "access"), "access") == 8


def test_secrets_round_trip_and_are_not_stored_in_clear() -> None:
    box = SecretBox("server-secret")
    sealed = box.seal("sk-or-v1-abcdef")
    assert "sk-or-v1-abcdef" not in sealed
    assert box.open(sealed) == "sk-or-v1-abcdef"


def test_a_secret_sealed_under_another_key_is_unreadable() -> None:
    sealed = SecretBox("old-secret").seal("sk-or-v1-abcdef")
    with pytest.raises(UnreadableSecret):
        SecretBox("new-secret").open(sealed)


def test_a_secret_sealed_under_a_previous_key_opens_during_a_rotation() -> None:
    sealed = SecretBox("old-secret").seal("sk-or-v1-abcdef")
    rotated = SecretBox("new-secret", fallback_keys=("old-secret",))

    assert rotated.open(sealed) == "sk-or-v1-abcdef"
    # What it seals now needs only the new key.
    assert SecretBox("new-secret").open(rotated.seal("sk-new")) == "sk-new"


def test_the_app_secret_box_takes_the_fallbacks_from_settings() -> None:
    sealed = SecretBox("old-secret-" + "x" * 32).seal("sk-or-v1-abcdef")
    settings = TEST_SETTINGS.model_copy(update={"secret_key_fallbacks": ["old-secret-" + "x" * 32]})
    assert secret_box_for(settings).open(sealed) == "sk-or-v1-abcdef"
    assert token_signer(settings).fallback_keys == ("old-secret-" + "x" * 32,)


def test_the_work_factor_of_a_hash_is_readable() -> None:
    assert hash_iterations(DJANGO_HASH) == 1000
    assert hash_iterations(hash_password("secret-pass", 12)) == 12
    assert hash_iterations("md5$1$salt$x") is None

"""Password hashing, token signing and credential encryption. Pure functions over
plain values, so the services and the tests use them without any web framework.

Hashes use Django's ``pbkdf2_sha256$<iterations>$<salt>$<base64 hash>`` format:
accounts imported from the previous Django backend verify unchanged, and new
hashes are the same algorithm at the configured work factor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal, Protocol, TypeGuard

import jwt
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

HASH_ALGORITHM = "pbkdf2_sha256"
SALT_ALPHABET = string.ascii_letters + string.digits
SALT_LENGTH = 22
JWT_ALGORITHM = "HS256"

#: HKDF context, so the encryption key differs from the JWT key derived from the
#: same SECRET_KEY (domain separation).
SECRET_BOX_CONTEXT = b"aimix provider credentials v1"

TokenType = Literal["access", "refresh"]


def hash_password(password: str, iterations: int) -> str:
    salt = "".join(secrets.choice(SALT_ALPHABET) for _ in range(SALT_LENGTH))
    return f"{HASH_ALGORITHM}${iterations}${salt}${_pbkdf2(password, salt, iterations)}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check; any hash this module cannot read simply fails."""
    parsed = _parse(encoded)
    if parsed is None:
        return False
    rounds, salt, expected = parsed
    return hmac.compare_digest(_pbkdf2(password, salt, rounds), expected)


def hash_iterations(encoded: str) -> int | None:
    """The work factor of a hash this module can verify, else None."""
    parsed = _parse(encoded)
    return parsed[0] if parsed is not None else None


def verify_nothing(password: str, iterations: int) -> None:
    """Spend what checking a real account's password costs, for a username that
    has none, so the response time does not tell which usernames exist."""
    verify_password(password, _decoy_hash(iterations))


@lru_cache(maxsize=4)
def _decoy_hash(iterations: int) -> str:
    """Computed once per work factor; nobody knows its password."""
    return hash_password(secrets.token_urlsafe(16), iterations)


def _parse(encoded: str) -> tuple[int, str, str] | None:
    """(iterations, salt, hash) of a hash this module can verify, else None."""
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        rounds = int(iterations)
    except ValueError:
        return None
    if algorithm != HASH_ALGORITHM or rounds < 1:
        return None
    return rounds, salt, expected


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return base64.b64encode(digest).decode("ascii")


@dataclass(frozen=True)
class TokenSubject:
    """Who a valid token was issued to, and the account's token version then."""

    user_id: int
    version: int


@dataclass(frozen=True)
class TokenSigner:
    """Issues and reads the API's JWTs (§7 Value Object over the signing config).

    Tokens are signed with ``secret_key``; ``fallback_keys`` (previous keys,
    during a rotation) are only accepted when reading one."""

    secret_key: str
    access_lifetime: timedelta
    refresh_lifetime: timedelta
    fallback_keys: tuple[str, ...] = ()

    def issue(self, user_id: int, token_type: TokenType, version: int = 0) -> str:
        now = datetime.now(timezone.utc)
        lifetime = self.access_lifetime if token_type == "access" else self.refresh_lifetime
        claims = {
            "token_type": token_type,
            "user_id": user_id,
            "ver": version,
            "iat": now,
            "exp": now + lifetime,
            "jti": secrets.token_hex(16),
        }
        return jwt.encode(claims, self.secret_key, algorithm=JWT_ALGORITHM)

    def subject(self, token: str, token_type: TokenType) -> TokenSubject | None:
        """Who a valid, unexpired token of the given type names, else None. A token
        issued before versions existed has none and counts as version 0."""
        claims = self._claims(token)
        user_id, version = claims.get("user_id"), claims.get("ver", 0)
        if claims.get("token_type") == token_type and _is_int(user_id) and _is_int(version):
            return TokenSubject(user_id, version)
        return None

    def user_id(self, token: str, token_type: TokenType) -> int | None:
        """The user a valid token of the given type was issued to, else None."""
        subject = self.subject(token, token_type)
        return subject.user_id if subject is not None else None

    def _claims(self, token: str) -> dict[str, object]:
        """The claims of a token signed by any accepted key; empty when invalid."""
        for key in (self.secret_key, *self.fallback_keys):
            try:
                claims: dict[str, object] = jwt.decode(
                    token, key, algorithms=[JWT_ALGORITHM], options={"require": ["exp"]}
                )
            except jwt.InvalidSignatureError:
                continue
            except jwt.PyJWTError:
                return {}
            return claims
        return {}


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


class UnreadableSecret(ValueError):
    """A stored secret cannot be decrypted — SECRET_KEY changed since it was saved."""


@dataclass(frozen=True)
class SecretBox:
    """Encrypts credentials at rest with Fernet (AES-CBC + HMAC), keyed by
    HKDF over SECRET_KEY. Secrets are sealed with ``secret_key`` and opened with
    it or any of ``fallback_keys`` (previous keys, during a rotation); one sealed
    under a key in neither stays unreadable."""

    secret_key: str
    fallback_keys: tuple[str, ...] = ()

    def _fernet(self) -> MultiFernet:
        return MultiFernet([_fernet(key) for key in (self.secret_key, *self.fallback_keys)])

    def seal(self, plaintext: str) -> str:
        return self._fernet().encrypt(plaintext.encode()).decode("ascii")

    def open(self, token: str) -> str:
        try:
            return self._fernet().decrypt(token.encode("ascii")).decode()
        except (InvalidToken, UnicodeError) as cause:
            raise UnreadableSecret("The stored secret cannot be decrypted.") from cause


def _fernet(secret_key: str) -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=SECRET_BOX_CONTEXT).derive(
        secret_key.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


class SigningKeys(Protocol):
    """Where the keys come from (``Settings``, structurally, so this module stays
    free of configuration)."""

    @property
    def secret_key(self) -> str: ...

    @property
    def secret_key_fallbacks(self) -> list[str]: ...


def secret_box_for(keys: SigningKeys) -> SecretBox:
    """The one way to build the app's ``SecretBox``: current key plus fallbacks."""
    return SecretBox(keys.secret_key, tuple(keys.secret_key_fallbacks))

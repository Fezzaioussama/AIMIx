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
from typing import Literal

import jwt
from cryptography.fernet import Fernet, InvalidToken
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
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        rounds = int(iterations)
    except ValueError:
        return False
    if algorithm != HASH_ALGORITHM or rounds < 1:
        return False
    return hmac.compare_digest(_pbkdf2(password, salt, rounds), expected)


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return base64.b64encode(digest).decode("ascii")


@dataclass(frozen=True)
class TokenSigner:
    """Issues and reads the API's JWTs (§7 Value Object over the signing config)."""

    secret_key: str
    access_lifetime: timedelta
    refresh_lifetime: timedelta

    def issue(self, user_id: int, token_type: TokenType) -> str:
        now = datetime.now(timezone.utc)
        lifetime = self.access_lifetime if token_type == "access" else self.refresh_lifetime
        claims = {
            "token_type": token_type,
            "user_id": user_id,
            "iat": now,
            "exp": now + lifetime,
            "jti": secrets.token_hex(16),
        }
        return jwt.encode(claims, self.secret_key, algorithm=JWT_ALGORITHM)

    def user_id(self, token: str, token_type: TokenType) -> int | None:
        """The user a valid token of the given type was issued to, else None."""
        try:
            claims = jwt.decode(token, self.secret_key, algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError:
            return None
        user_id = claims.get("user_id")
        if claims.get("token_type") != token_type or not isinstance(user_id, int):
            return None
        return user_id


class UnreadableSecret(ValueError):
    """A stored secret cannot be decrypted — SECRET_KEY changed since it was saved."""


@dataclass(frozen=True)
class SecretBox:
    """Encrypts credentials at rest with Fernet (AES-CBC + HMAC), keyed by
    HKDF over SECRET_KEY. Changing SECRET_KEY makes saved secrets unreadable."""

    secret_key: str

    def _fernet(self) -> Fernet:
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=SECRET_BOX_CONTEXT).derive(
            self.secret_key.encode()
        )
        return Fernet(base64.urlsafe_b64encode(key))

    def seal(self, plaintext: str) -> str:
        return self._fernet().encrypt(plaintext.encode()).decode("ascii")

    def open(self, token: str) -> str:
        try:
            return self._fernet().decrypt(token.encode("ascii")).decode()
        except (InvalidToken, UnicodeError) as cause:
            raise UnreadableSecret("The stored secret cannot be decrypted.") from cause

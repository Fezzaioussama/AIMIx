"""Secret links, a webhook's and a shared run's (AGENTS.md §3): a random token only the
owner's screen reads, kept as its SHA-256 digest (to look it up: the table holds no
link) and sealed in the server's secret box (so the owner can read the link again)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from api.security import SecretBox

#: Random bytes in a token: 256 bits, so a link cannot be guessed.
TOKEN_BYTES = 32


@dataclass(frozen=True)
class SealedToken:
    """A new token as it is stored: its digest and its sealed form (§7 Value Object)."""

    token: str
    hash: str
    sealed: str


def token_hash(token: str) -> str:
    """How a token is looked up: its SHA-256 digest, so the table holds no link."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(box: SecretBox) -> SealedToken:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return SealedToken(token, token_hash(token), box.seal(token))

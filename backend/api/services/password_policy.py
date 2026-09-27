"""Password rules for new accounts: the four checks the Django backend applied.

The common-password list is Django's (BSD-licensed), copied to
``api/data/common-passwords.txt.gz`` so the check survives the migration.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Callable
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

MIN_LENGTH = 8
MAX_SIMILARITY = 0.7
COMMON_PASSWORDS_FILE = Path(__file__).resolve().parents[1] / "data" / "common-passwords.txt.gz"

Rule = Callable[[str, str], str | None]


def problems(password: str, username: str) -> list[str]:
    """Every rule the password breaks, as user-facing sentences (empty = fine)."""
    return [message for rule in RULES if (message := rule(password, username))]


def _too_short(password: str, _username: str) -> str | None:
    if len(password) >= MIN_LENGTH:
        return None
    return f"This password is too short. It must contain at least {MIN_LENGTH} characters."


def _too_similar_to_username(password: str, username: str) -> str | None:
    lowered = password.lower()
    name = username.lower()
    for part in [*re.split(r"\W+", name), name]:
        if _negligible(part, lowered):
            continue
        if SequenceMatcher(a=lowered, b=part).quick_ratio() >= MAX_SIMILARITY:
            return "The password is too similar to the username."
    return None


def _negligible(part: str, password: str) -> bool:
    """A short name fragment inside a much longer password is not a resemblance."""
    if not part:
        return True
    return len(password) >= 10 * len(part) and len(part) < MAX_SIMILARITY / 2 * len(password)


def _too_common(password: str, _username: str) -> str | None:
    if password.lower().strip() in _common_passwords():
        return "This password is too common."
    return None


def _entirely_numeric(password: str, _username: str) -> str | None:
    return "This password is entirely numeric." if password.isdigit() else None


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    with gzip.open(COMMON_PASSWORDS_FILE, "rt", encoding="utf-8") as lines:
        return frozenset(line.strip() for line in lines)


#: Adding a rule is one entry here (§5 O).
RULES: tuple[Rule, ...] = (
    _too_similar_to_username,
    _too_short,
    _too_common,
    _entirely_numeric,
)

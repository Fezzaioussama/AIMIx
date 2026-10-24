"""Field types shared by several contracts (§3)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from api.services.catalog import known_model_ids, provider_names

#: Trimmed text that must not be empty.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _assume_utc(value: datetime) -> datetime:
    # SQLite drops the offset; every timestamp is stored in UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


#: A stored timestamp, sent with its UTC offset.
UtcDateTime = Annotated[datetime, AfterValidator(_assume_utc)]


def ensure_member(kind: str, value: str, allowed: list[str]) -> str:
    """Return ``value`` if it is one of ``allowed``, else raise naming the options."""
    if value not in allowed:
        raise ValueError(f"Unknown {kind} '{value}'. Choose one of: {', '.join(allowed)}.")
    return value


def _member_of(kind: str, allowed: Callable[[], list[str]]) -> AfterValidator:
    return AfterValidator(lambda value: ensure_member(kind, value, allowed()))


#: A model id some provider catalogue lists. A stale id used to be stored
#: happily and only fail later at run time, as an empty result rather than an
#: error. Which provider runs it is per user, so GET /models narrows the choice.
ModelId = Annotated[str, _member_of("model", known_model_ids)]

ProviderName = Annotated[str, _member_of("provider", provider_names)]

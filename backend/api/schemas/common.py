"""Field types shared by several request contracts (§3)."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from api.services.catalog import available_model_ids

#: Trimmed text that must not be empty.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _known_model(value: str) -> str:
    """Reject model ids the provider layer does not know about.

    A stale id used to be stored happily and only fail later at run time, as an
    empty result rather than an error.
    """
    allowed = available_model_ids()
    if value not in allowed:
        raise ValueError(f"Unknown model '{value}'. Choose one of: {', '.join(allowed)}.")
    return value


ModelId = Annotated[str, AfterValidator(_known_model)]

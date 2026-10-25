"""Field types shared by several contracts (§3)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from api.models import PIPELINE_INPUT_NAME_MAX_LENGTH, PIPELINE_MAX_INPUTS
from api.services.catalog import known_model_ids, provider_names

#: Trimmed text that must not be empty.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
#: Trimmed text, possibly empty.
Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]

#: What a pipeline may hold: steps, and characters in one step's prompt.
PIPELINE_MAX_STEPS = 50
STEP_PROMPT_MAX_LENGTH = 50_000
#: Characters one run may be given in all, its free text and named inputs
#: together: room for a few attached documents at DOCUMENT_MAX_CHARS's default.
RUN_INPUT_MAX_LENGTH = 500_000

#: A run's value for each named input, by input name.
RunInputValues = Annotated[
    dict[Annotated[str, StringConstraints(max_length=PIPELINE_INPUT_NAME_MAX_LENGTH)], Trimmed],
    Field(max_length=PIPELINE_MAX_INPUTS),
]


def ensure_run_input_size(text: str | None, values: Mapping[str, str] | None) -> None:
    """Refuse a run given more than RUN_INPUT_MAX_LENGTH characters in all."""
    size = len(text or "") + sum(len(value) for value in (values or {}).values())
    if size > RUN_INPUT_MAX_LENGTH:
        raise ValueError(
            f"A run can be given at most {RUN_INPUT_MAX_LENGTH:,} characters in all; "
            f"this one has {size:,}."
        )


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

"""Building blocks shared by the settings modules (``config/*_settings.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, AliasChoices, BeforeValidator
from pydantic_settings import NoDecode

BASE_DIR = Path(__file__).resolve().parents[1]

#: Values that look like a filled-in credential but are not one. Treating these
#: as unset means a half-configured .env fails fast with "not configured"
#: instead of sending a doomed request and reporting an upstream 401.
SECRET_PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "your-api-key",
        "your-api-key-here",
        "your_api_key",
        "your_api_key_here",
    }
)


def env_aliases(*names: str) -> AliasChoices:
    """Accept a variable under its current name and any legacy spelling."""
    return AliasChoices(*names)


def _split_commas(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def _drop_placeholder(value: str) -> str:
    value = value.strip()
    return "" if value.lower() in SECRET_PLACEHOLDERS else value


def _empty_is_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


#: ``a,b, c`` in the environment; a list in code.
CommaList = Annotated[list[str], NoDecode, BeforeValidator(_split_commas)]
#: A credential: surrounding blanks are dropped and a placeholder means unset.
Secret = Annotated[str, AfterValidator(_drop_placeholder)]
#: On an optional limit: ``X=`` (empty or blank) in the environment means unset (None).
EmptyIsNone = BeforeValidator(_empty_is_none)

"""Contracts for the Integrations section: a user's own MCP servers.

Responses never contain a header value, only its name and ``hint`` (its last
characters, when the value is long enough to hint at).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from api.models import INTEGRATION_NAME_PATTERN, INTEGRATION_URL_MAX_LENGTH
from api.schemas.common import UtcDatetime

INTEGRATION_MAX_HEADERS = 10
HEADER_NAME_MAX_LENGTH = 100
HEADER_VALUE_MAX_LENGTH = 4096
#: Headers the HTTP client and the MCP transport set themselves.
RESERVED_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "mcp-protocol-version",
        "mcp-session-id",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

IntegrationName = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=f"^{INTEGRATION_NAME_PATTERN}$")
]
#: No spaces or control characters; the service checks the scheme and host.
IntegrationUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=INTEGRATION_URL_MAX_LENGTH,
        pattern=r"^[^\s\x00-\x1f\x7f]+$",
    ),
]
#: An HTTP header name (RFC 9110 token).
HeaderName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=HEADER_NAME_MAX_LENGTH,
        pattern=r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$",
    ),
]
#: No control characters, so a value can never start another header.
HeaderValue = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=HEADER_VALUE_MAX_LENGTH,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]


class HeaderIn(BaseModel):
    name: HeaderName
    #: Omitted or null keeps the value saved under this name (on an update).
    value: HeaderValue | None = None

    @field_validator("name")
    @classmethod
    def _not_reserved(cls, name: str) -> str:
        if name.lower() in RESERVED_HEADERS:
            raise ValueError(f"The {name} header is set automatically and cannot be changed.")
        return name


def _ensure_unique_names(headers: Sequence[HeaderIn]) -> None:
    """HTTP header names are case-insensitive, so ``x-key`` and ``X-Key`` clash."""
    names = [header.name.lower() for header in headers]
    if len(set(names)) != len(names):
        raise ValueError("Each header may appear only once.")


class IntegrationIn(BaseModel):
    """Body of POST /api/integrations."""

    name: IntegrationName
    url: IntegrationUrl
    enabled: bool = True
    headers: list[HeaderIn] = Field(default_factory=list, max_length=INTEGRATION_MAX_HEADERS)

    @field_validator("headers")
    @classmethod
    def _complete_headers(cls, headers: list[HeaderIn]) -> list[HeaderIn]:
        _ensure_unique_names(headers)
        if any(header.value is None for header in headers):
            raise ValueError("Enter a value for every header.")
        return headers


class IntegrationPatch(BaseModel):
    """Body of PATCH /api/integrations/{id}: omitted fields keep their value.

    ``headers``, when sent, is the complete list: a header left out is removed,
    and a header sent without a value keeps its saved one.
    """

    name: IntegrationName | None = None
    url: IntegrationUrl | None = None
    enabled: bool | None = None
    headers: list[HeaderIn] | None = Field(None, max_length=INTEGRATION_MAX_HEADERS)

    @field_validator("headers")
    @classmethod
    def _unique_headers(cls, headers: list[HeaderIn] | None) -> list[HeaderIn] | None:
        _ensure_unique_names(headers or [])
        return headers


class HeaderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    #: Last characters of the value; empty when the value is too short to hint at.
    hint: str


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    enabled: bool
    headers: list[HeaderOut]
    created_at: UtcDatetime


class IntegrationToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #: The name agents and a step's ``allowed_tools`` use: ``<integration>_<tool>``.
    name: str
    description: str


class IntegrationTestOut(BaseModel):
    tools: list[IntegrationToolOut]

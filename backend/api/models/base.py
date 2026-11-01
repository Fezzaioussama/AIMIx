"""What every model shares: the declarative base, the constraint names Alembic relies on,
how a status enum is stored, and the column sizes the API contracts validate against."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

STEP_TITLE_MAX_LENGTH = 100
STEP_ROLE_MAX_LENGTH = 100
STEP_EXPECTED_OUTPUT_MAX_LENGTH = 500
USERNAME_MAX_LENGTH = 150
PIPELINE_NAME_MAX_LENGTH = 255
#: A named run input is referenced as ``{name}`` in step prompts. ``input`` is
#: reserved because ``{input}`` already means a stage's input.
PIPELINE_INPUT_NAME_PATTERN = r"[a-z][a-z0-9_]*"
PIPELINE_INPUT_NAME_MAX_LENGTH = 40
PIPELINE_INPUT_LABEL_MAX_LENGTH = 100
PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH = 300
PIPELINE_MAX_INPUTS = 20
RESERVED_INPUT_NAME = "input"
#: ``{feedback}`` is a reviewer's feedback while a step is redone (review loops).
FEEDBACK_PLACEHOLDER = "feedback"
#: What a step's "run only if" condition compares with, at most this many characters.
STEP_CONDITION_VALUE_MAX_LENGTH = 200
#: A review loop may send the work back at most this many times.
STEP_REVIEW_MAX_ROUNDS = 5
MODEL_ID_MAX_LENGTH = 200
PROVIDER_NAME_MAX_LENGTH = 50
API_KEY_HINT_LENGTH = 4
#: An integration's name prefixes its tools' names (``<name>_<tool>``).
INTEGRATION_NAME_PATTERN = r"[a-z][a-z0-9_]{1,30}"
INTEGRATION_NAME_MAX_LENGTH = 31
INTEGRATION_URL_MAX_LENGTH = 2048
STATUS_MAX_LENGTH = 16
ERROR_CODE_MAX_LENGTH = 64
#: Model APIs accept tool names up to 64 characters; longer ones are cut when stored.
TOOL_NAME_MAX_LENGTH = 64
#: Where a tool comes from: an integration's name, or a fixed label.
TOOL_SOURCE_MAX_LENGTH = 64
#: Long enough for any IANA time zone name ("America/Argentina/ComodRivadavia").
TIMEZONE_MAX_LENGTH = 64
#: A SHA-256 digest in hex, how a webhook's secret token is looked up.
TOKEN_HASH_LENGTH = 64
#: The longest host name DNS allows.
HOST_MAX_LENGTH = 253


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Deterministic constraint names, so Alembic migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _status_type(statuses: type[Enum]) -> SQLEnum:
    """Stored as the lowercase value in a plain string column, read back as the enum."""
    return SQLEnum(
        statuses,
        native_enum=False,
        length=STATUS_MAX_LENGTH,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )

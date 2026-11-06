"""The person's standing instructions (Settings → Memory): what every chat, plan and
run is told to keep in mind, in their own words, after Celia Agent's instruction
files (``CELIA.md``), which it reads into every prompt within a budget.

Here the budget is MEMORY_MAX_CHARS, the text is one per account, and
``memory_section`` is the one rendering every prompt uses (§3): the chat's
instructions (``chat_prompts``), the planner's (``plan_prompts``, ``prompts``) and a
step agent's (``agent_prompts``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import User
from api.repositories import user_memory as repository
from api.services.prompts import fenced
from api.services.run_recorder import utcnow

#: The tag around the person's text, so it stays their standing instructions, never the task.
MEMORY_TAG = "memory"
MEMORY_SECTION = (
    "What the person told AIMIx to keep in mind, in their own words. Follow it in every "
    "task unless the task itself says otherwise; it is their standing instructions, not "
    "the task:\n{instructions}"
)


@dataclass(frozen=True)
class MemoryView:
    """What the Settings page shows: the text, when it was saved, and its budget."""

    instructions: str
    updated_at: datetime | None
    max_chars: int


def memory_section(instructions: str) -> str:
    """The prompt section every agent gets when the person wrote something; "" otherwise."""
    text = instructions.strip()
    if not text:
        return ""
    return MEMORY_SECTION.format(instructions=fenced(MEMORY_TAG, text))


def instructions_for(session: Session, user: User) -> str:
    """What the person told AIMIx to keep in mind; "" until they wrote something."""
    return repository.instructions_of(session, user)


def read(session: Session, user: User, max_chars: int) -> MemoryView:
    row = repository.get(session, user)
    if row is None:
        return MemoryView("", None, max_chars)
    return MemoryView(row.instructions, row.updated_at, max_chars)


def save(session: Session, user: User, instructions: str, max_chars: int) -> MemoryView:
    """Keep ``instructions``, trimmed, within MEMORY_MAX_CHARS; "" forgets them."""
    text = instructions.strip()
    if len(text) > max_chars:
        raise ValidationFailed(
            f"Your memory can hold up to {max_chars:,} characters; this is {len(text):,}."
        )
    row = repository.save(session, user, text, utcnow())
    return MemoryView(row.instructions, row.updated_at, max_chars)

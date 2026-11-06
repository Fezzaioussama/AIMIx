from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field

from api.models import CHAT_TITLE_MAX_LENGTH, TIMEZONE_MAX_LENGTH, ChatRole
from api.schemas.common import NonBlank, Trimmed, UtcDateTime
from api.schemas.usage import UsageOut
from api.services.chat_events import ToolStatus
from api.services.usage import step_usage, total_usage

#: The longest chat message: a long question with some pasted text.
CHAT_PROMPT_MAX_LENGTH = 100_000
#: The most earlier messages one request may carry; of those, the assistant reads the
#: newest that fit in CHAT_HISTORY_MAX_CHARS.
CHAT_HISTORY_MAX_TURNS = 200


class ChatTurnIn(BaseModel):
    """One earlier message of the conversation, as the chat screen showed it."""

    role: Literal["user", "assistant"]
    content: Annotated[str, Field(max_length=CHAT_PROMPT_MAX_LENGTH)]


class ChatRequest(BaseModel):
    """Contract for POST /api/chat."""

    prompt: Annotated[NonBlank, Field(max_length=CHAT_PROMPT_MAX_LENGTH)]
    #: A chat kept on the server (POST /chats): the assistant reads its messages, and
    #: both sides of this exchange are added to it. ``history`` is then ignored.
    chat_id: int | None = None
    #: What was said before the prompt, oldest first, for a chat the server does not keep.
    history: Annotated[list[ChatTurnIn], Field(max_length=CHAT_HISTORY_MAX_TURNS)] = Field(
        default_factory=list
    )
    #: The browser's IANA time zone ("Europe/Paris"); one the server does not know is ignored.
    timezone: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=TIMEZONE_MAX_LENGTH)]
        | None
    ) = None


ChatTitle = Annotated[Trimmed, Field(max_length=CHAT_TITLE_MAX_LENGTH)]


class ChatIn(BaseModel):
    """A new chat; left empty, its title is the first line of its first message."""

    title: ChatTitle = ""


class ChatPatch(BaseModel):
    title: Annotated[NonBlank, Field(max_length=CHAT_TITLE_MAX_LENGTH)]


class ChatOut(BaseModel):
    """A chat in the list: when it was last written to, never its messages."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ChatToolOut(BaseModel):
    """One tool a reply used, as the chat screen showed it."""

    tool: str
    label: str
    status: ToolStatus
    detail: str = ""
    action: dict[str, Any] | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: ChatRole
    text: str
    tools: list[ChatToolOut]
    created_at: UtcDateTime
    #: Read to add up the message's usage, which ``usage`` says in one object.
    input_tokens: int = Field(0, exclude=True)
    output_tokens: int = Field(0, exclude=True)
    cost_usd: float | None = Field(None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usage(self) -> UsageOut:
        """What the model calls behind this message used and cost."""
        return UsageOut.model_validate(step_usage(self))


class ChatDetailOut(ChatOut):
    """A whole chat: its messages, oldest first, and what they used in all."""

    messages: list[ChatMessageOut]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usage(self) -> UsageOut:
        return UsageOut.model_validate(total_usage(self.messages))

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

from api.schemas.common import UtcDateTime, none_if_empty


class DeliveryOut(BaseModel):
    """Where a pipeline's results go, as its owner's card shows it: the address's
    host and last characters only, never the whole address."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    pipeline_name: str
    destination: str
    hint: str
    #: "Slack", "Discord" or "Webhook" (any other https address, sent JSON).
    service: str
    #: Nothing is sent until its owner confirms it (POST .../confirm).
    confirmed: bool
    enabled: bool
    last_sent_at: UtcDateTime | None
    #: Why the latest sending failed; null when it was delivered.
    last_error: Annotated[str | None, BeforeValidator(none_if_empty)]


class DeliveryPatch(BaseModel):
    """Stop sending a workflow's results, or send them again (once confirmed)."""

    enabled: bool

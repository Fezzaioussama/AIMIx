from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict

from api.schemas.common import UtcDateTime, none_if_empty


class WebhookOut(BaseModel):
    """A webhook as its owner sees it in a list: never its token."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    pipeline_name: str
    enabled: bool
    last_called_at: UtcDateTime | None
    #: Why its latest call started no run; null when it started one.
    last_error: Annotated[str | None, BeforeValidator(none_if_empty)]


class WebhookLinkOut(WebhookOut):
    """One webhook with its token, which only its owner reads: the link is
    ``/api/hooks/<token>`` on this server."""

    token: str


class WebhookPatch(BaseModel):
    """Switch a webhook off (its link answers like an unknown one) or on again."""

    enabled: bool


class WebhookCallOut(BaseModel):
    """What a webhook call answers: the run it queued, to follow by its owner."""

    run_id: int
    status: Literal["queued"] = "queued"

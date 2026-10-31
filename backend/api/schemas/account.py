"""Contracts of the account routes: change the password, take a copy of the
account's data, delete the account."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.models import ScheduleFrequency
from api.schemas.approvals import RunApprovalOut
from api.schemas.auth import PASSWORD_MAX_LENGTH
from api.schemas.common import UtcDateTime
from api.schemas.files import FileOut
from api.schemas.integrations import HeaderOut
from api.schemas.pipelines import PipelineOut
from api.schemas.runs import RunOut

#: What the copy leaves out, written into it.
EXPORT_NOTE = (
    "Saved API keys and integration header values are secrets: only their last "
    "characters are included. Your files are listed; download them from the Files page."
)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class AccountDeleteIn(BaseModel):
    """The account's password, asked again so a left-open session cannot delete it."""

    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    created_at: UtcDateTime
    #: The provider chosen on the Settings page; null is the server's default.
    llm_provider: str | None


class ProviderSettingExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    default_model: str
    api_key_hint: str


class ScheduleExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    frequency: ScheduleFrequency
    hour: int
    minute: int
    weekday: int | None
    day_of_month: int | None
    timezone: str
    input: str = Field(validation_alias="input_text")
    inputs: dict[str, str] = Field(validation_alias="input_values")
    max_cost_usd: float | None
    max_tokens: int | None
    enabled: bool
    next_run_at: UtcDateTime | None
    last_error: str
    created_at: UtcDateTime


class IntegrationExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    enabled: bool
    require_approval: bool
    headers: list[HeaderOut] = Field(validation_alias="header_hints")
    created_at: UtcDateTime


class ApprovalExportOut(RunApprovalOut):
    """An approval request of any status, with the run it belongs to."""

    run_id: int
    decided_at: UtcDateTime | None


class AccountExportOut(BaseModel):
    """Response of GET /api/account/export, sent as a JSON file to save."""

    model_config = ConfigDict(from_attributes=True)

    exported_at: UtcDateTime
    account: AccountOut
    provider_settings: list[ProviderSettingExportOut]
    pipelines: list[PipelineOut]
    #: Newest first, each with its inputs, steps and outputs.
    runs: list[RunOut]
    approvals: list[ApprovalExportOut]
    schedules: list[ScheduleExportOut]
    integrations: list[IntegrationExportOut]
    files: list[FileOut]
    note: str = EXPORT_NOTE

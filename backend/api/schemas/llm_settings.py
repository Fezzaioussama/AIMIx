"""Contracts for the Settings page: provider, API keys and default models.

Responses never contain a key, only ``key_hint`` (its last characters).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from api.models import MODEL_ID_MAX_LENGTH
from api.schemas.common import ProviderName, ensure_member
from api.services.catalog import available_model_ids

API_KEY_MAX_LENGTH = 512

#: A pasted key, trimmed; it may not be blank or contain spaces.
ApiKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=API_KEY_MAX_LENGTH, pattern=r"^\S+$"
    ),
]


class ProviderSettingsIn(BaseModel):
    name: ProviderName
    default_model: str = Field(max_length=MODEL_ID_MAX_LENGTH)
    #: Omitted or null keeps the saved key; DELETE .../keys/{provider} removes it.
    api_key: ApiKey | None = None

    @model_validator(mode="after")
    def _model_belongs_to_provider(self) -> ProviderSettingsIn:
        ensure_member("model", self.default_model, available_model_ids(self.name))
        return self


class LLMSettingsIn(BaseModel):
    """Body of PUT /api/llm-settings."""

    provider: ProviderName
    providers: list[ProviderSettingsIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_providers(self) -> LLMSettingsIn:
        names = [entry.name for entry in self.providers]
        if len(set(names)) != len(names):
            raise ValueError("Each provider may appear only once.")
        return self


class ProviderSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    #: Where the key in use comes from: saved here, backend/.env, or nowhere.
    key_source: Literal["saved", "environment", "none"]
    key_hint: str
    default_model: str
    models: list[str]


class LLMSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    providers: list[ProviderSettingsOut]

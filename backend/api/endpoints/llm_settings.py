"""The signed-in user's LLM provider, API keys and default models."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import CurrentUser, DbSession, Secrets
from api.schemas.common import ProviderName
from api.schemas.llm_settings import LLMSettingsIn, LLMSettingsOut
from api.services import llm_settings as service

router = APIRouter(prefix="/llm-settings", tags=["llm-settings"])


def _update(body: LLMSettingsIn) -> service.SettingsUpdate:
    return service.SettingsUpdate(
        provider=body.provider,
        providers=[
            service.ProviderChoice(entry.name, entry.default_model, entry.api_key)
            for entry in body.providers
        ],
    )


@router.get("")
def read_settings(user: CurrentUser, session: DbSession) -> LLMSettingsOut:
    return LLMSettingsOut.model_validate(service.read(session, user))


@router.put("")
def save_settings(
    body: LLMSettingsIn, user: CurrentUser, session: DbSession, box: Secrets
) -> LLMSettingsOut:
    return LLMSettingsOut.model_validate(service.save(session, user, box, _update(body)))


@router.delete("/keys/{provider}")
def remove_key(provider: ProviderName, user: CurrentUser, session: DbSession) -> LLMSettingsOut:
    return LLMSettingsOut.model_validate(service.remove_key(session, user, provider))

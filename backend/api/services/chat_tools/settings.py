"""Chat tools that show the person's model and connected apps, and change the model
their agents use. Keys, and adding or changing a connection, stay on the Settings
screen: neither a key nor a server address the person did not type passes through
the model (a page it read could ask it to add one)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from langchain.tools import tool
from langchain_core.tools import BaseTool, ToolException

from api.exceptions import DomainError
from api.repositories import integrations as integration_repository
from api.schemas.llm_settings import LLMSettingsIn
from api.security import secret_box_for
from api.services import llm_settings
from api.services.chat_tools.common import refused, session_user
from api.services.chat_tools.scope import ChatScope
from config.settings import get_settings


def settings_summary(view: llm_settings.SettingsView) -> dict[str, Any]:
    """The model settings as the chat tells them: never a key, only whether one is there."""
    active = next(item for item in view.providers if item.name == view.provider)
    return {
        "provider": view.provider,
        "default_model": active.default_model,
        "providers": [
            {
                "name": item.name,
                "has_key": item.key_source != "none",
                "default_model": item.default_model,
            }
            for item in view.providers
        ],
    }


def settings_tools(scope: ChatScope) -> list[BaseTool]:
    """Bind the settings tools to the signed-in person."""

    @tool
    def show_settings() -> dict[str, Any]:
        """Show which model provider and default model your agents use, which
        providers have a key, and your connected apps (integrations): each one's
        name, host, whether it is on and whether its tools ask before they act."""
        with scope.database.session() as session:
            owner = session_user(session, scope.user)
            apps = integration_repository.for_user(session, owner)
            return {
                **settings_summary(llm_settings.read(session, owner)),
                "connected_apps": [
                    {
                        "name": app.name,
                        "host": urlsplit(app.url).hostname,
                        "on": app.enabled,
                        "asks_first": app.require_approval,
                    }
                    for app in apps
                ],
            }

    @tool
    def set_default_model(model: str, provider: str | None = None) -> dict[str, Any]:
        """Choose the model your agents and this chat use by default (see
        list_models). Give provider to switch to another provider; it needs a key
        saved in Settings first."""
        try:
            with scope.database.session() as session:
                owner = session_user(session, scope.user)
                current = llm_settings.read(session, owner)
                chosen = provider or current.provider
                body = LLMSettingsIn.model_validate(
                    {"provider": chosen, "providers": [{"name": chosen, "default_model": model}]}
                )
                target = next(item for item in current.providers if item.name == body.provider)
                if target.key_source == "none":
                    raise ToolException(
                        f"{body.provider} has no API key yet: add one in Settings first."
                    )
                update = llm_settings.SettingsUpdate(
                    body.provider,
                    [llm_settings.ProviderChoice(body.provider, body.providers[0].default_model)],
                )
                view = llm_settings.save(session, owner, secret_box_for(get_settings()), update)
                return settings_summary(view)
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    return [show_settings, set_default_model]

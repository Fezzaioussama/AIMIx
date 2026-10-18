"""Toolbox configuration, copied out of the settings once (AGENTS.md §5 D)."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import Settings


@dataclass(frozen=True)
class ToolboxConfig:
    """Limits and credentials the built-in tools need (§7 Value Object).

    An empty ``search_api_key`` means web search is not configured.
    """

    enabled: tuple[str, ...]
    timeout_seconds: float
    fetch_max_bytes: int
    fetch_max_chars: int
    search_url: str
    search_max_results: int
    # Kept out of repr, so a logged config never shows it.
    search_api_key: str = field(default="", repr=False)


def toolbox_config(settings: Settings) -> ToolboxConfig:
    return ToolboxConfig(
        enabled=tuple(settings.agent_builtin_tools),
        timeout_seconds=settings.web_timeout_seconds,
        fetch_max_bytes=settings.web_fetch_max_bytes,
        fetch_max_chars=settings.web_fetch_max_chars,
        search_url=settings.tavily_search_url,
        search_max_results=settings.web_search_max_results,
        search_api_key=settings.tavily_api_key,
    )

"""Provider failures as the SDKs raise them, and a clock that never waits.

Shared by the retry tests; nothing here touches the network.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import httpx2
import openai
from openrouter.errors import OpenRouterDefaultError

from llm.base import ProviderConfig
from llm.retry import RetryClock, RetryPolicy

URL = "https://provider.test/v1/chat/completions"
#: "Now" for every Retry-After date, so waits are exact.
NOW = 1_700_000_000.0

SECRET_KEY = "sk-secret-test-key"
#: The documented default policy.
CONFIG = ProviderConfig(
    api_key=SECRET_KEY,
    default_model="vendor/model",
    timeout_seconds=5.0,
    retry=RetryPolicy(max_retries=2, base_delay_seconds=1.0, max_delay_seconds=20.0),
)
#: Retries on, waits off: the real clock then sleeps for zero seconds.
INSTANT = replace(CONFIG, retry=replace(CONFIG.retry, base_delay_seconds=0, max_delay_seconds=0))


class FakeClock:
    """Records each wait instead of sleeping; jitter always draws its upper bound."""

    def __init__(self) -> None:
        self.waits: list[float] = []
        self.bounds: list[tuple[float, float]] = []

    def _uniform(self, low: float, high: float) -> float:
        self.bounds.append((low, high))
        return high

    async def _async_sleep(self, seconds: float) -> None:
        self.waits.append(seconds)

    def retry_clock(self) -> RetryClock:
        return RetryClock(
            sleep=self.waits.append,
            async_sleep=self._async_sleep,
            now=lambda: NOW,
            uniform=self._uniform,
        )


def openai_status(status: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    """What the openai SDK raises for an HTTP error (direct providers, TogetherAI agents)."""
    response = httpx2.Response(status, headers=headers, request=httpx2.Request("POST", URL))
    return openai.APIStatusError(f"HTTP {status}", response=response, body=None)


def openrouter_status(status: int, headers: dict[str, str] | None = None) -> OpenRouterDefaultError:
    """What the openrouter SDK raises for an HTTP error (OpenRouter agents)."""
    response = httpx.Response(status, headers=headers, request=httpx.Request("POST", URL))
    return OpenRouterDefaultError(f"HTTP {status}", response)


def openai_connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx2.Request("POST", URL))


def openai_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx2.Request("POST", URL))

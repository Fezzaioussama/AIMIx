"""Bounded retries for transient provider failures (AGENTS.md §6).

The one retry policy for every model call: the direct provider (``base.py``)
and the LangChain chat models the agents use (``agent_models.py``). The SDKs'
own retries stay off, because none of them can express this policy.

- Only a transient failure is retried: a connection that failed or dropped,
  and HTTP 408, 429, 500, 502, 503 and 504. Any other status fails at once, and
  so does a client-side timeout: LLM_TIMEOUT_SECONDS is long, so another
  attempt would multiply the wait rather than shorten it.
- At most ``max_retries`` retries. Each waits the provider's ``Retry-After``
  when it sent one, else a random time up to ``base * 2**retry`` (exponential
  backoff with full jitter), and never longer than ``max_delay``.
- A stream is retried only until it yields its first item, so output that was
  already handed on is never produced twice.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import math
import random
import time
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Mapping,
)
from dataclasses import dataclass
from typing import TypeVar

import httpx
import openai
from openrouter.errors import NoResponseError, OpenRouterError

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Statuses that usually clear on their own: request timeout, rate limit, and
#: server or gateway failures.
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

#: How each SDK reports an HTTP error status.
STATUS_ERRORS: tuple[type[Exception], ...] = (openai.APIStatusError, OpenRouterError)

#: The request got no answer: a refused, reset or dropped connection. The
#: openai class is also the parent of its timeout, which is excluded by name.
CONNECTION_ERRORS: tuple[type[Exception], ...] = (
    openai.APIConnectionError,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    NoResponseError,
)

#: The only errors a retry loop catches; anything else propagates untouched.
_CANDIDATES = (*STATUS_ERRORS, *CONNECTION_ERRORS)


@dataclass(frozen=True)
class RetryPolicy:
    """How patiently a transient failure is retried (§7 Value Object)."""

    max_retries: int
    base_delay_seconds: float
    max_delay_seconds: float

    def delay(
        self, retry: int, retry_after: float | None, uniform: Callable[[float, float], float]
    ) -> float:
        """Seconds to wait before retry number ``retry``, counted from 0."""
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.max_delay_seconds)
        return uniform(0.0, min(self.max_delay_seconds, self.base_delay_seconds * 2.0**retry))


#: A single attempt: what a ``ProviderConfig`` built without a policy gets.
NO_RETRIES = RetryPolicy(max_retries=0, base_delay_seconds=0.0, max_delay_seconds=0.0)


@dataclass(frozen=True)
class RetryClock:
    """Where a retry loop gets time and chance; tests pass one that never waits."""

    sleep: Callable[[float], None] = time.sleep
    async_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    now: Callable[[], float] = time.time
    uniform: Callable[[float, float], float] = random.uniform


SYSTEM_CLOCK = RetryClock()


def is_timeout(error: BaseException) -> bool:
    """SDKs surface timeouts under different class names; match on the name so
    this check does not depend on either SDK's exception hierarchy."""
    return "timeout" in type(error).__name__.lower()


def _http_response(error: BaseException) -> tuple[int, Mapping[str, str]] | None:
    """The status and headers of an SDK status error; each SDK keeps them apart."""
    if isinstance(error, openai.APIStatusError):
        return error.status_code, error.response.headers
    if isinstance(error, OpenRouterError):
        return error.status_code, error.headers
    return None


def transient_reason(error: BaseException) -> str | None:
    """Why ``error`` deserves another attempt, or None when it does not."""
    response = _http_response(error)
    if response is not None:
        status = response[0]
        return f"http_{status}" if status in RETRYABLE_STATUS_CODES else None
    if isinstance(error, CONNECTION_ERRORS) and not is_timeout(error):
        return type(error).__name__
    return None


def retry_after_seconds(error: BaseException, now: float) -> float | None:
    """The wait the provider asked for in ``Retry-After``: a number of seconds
    or an HTTP date. None when it sent none, or one that cannot be read."""
    response = _http_response(error)
    value = response[1].get("retry-after") if response is not None else None
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return _seconds_until(value, now)
    return None if math.isnan(seconds) else seconds


def _seconds_until(http_date: str, now: float) -> float | None:
    parsed = email.utils.parsedate_tz(http_date)
    if parsed is None:
        return None
    try:
        return email.utils.mktime_tz(parsed) - now
    except (OverflowError, ValueError):
        return None


class Retrier:
    """Runs one model's calls under a RetryPolicy and logs every retry (§6).

    The last failure propagates unchanged, so callers map errors exactly as
    they would without retries.
    """

    def __init__(
        self, policy: RetryPolicy, provider: str, model: str, clock: RetryClock = SYSTEM_CLOCK
    ) -> None:
        self.policy = policy
        self.provider = provider
        self.model = model
        self.clock = clock

    def call(self, send: Callable[[], T]) -> T:
        retry = 0
        while True:
            try:
                return send()
            except _CANDIDATES as error:
                delay = self._wait_before_retry(error, retry)
                if delay is None:
                    raise
            self.clock.sleep(delay)
            retry += 1

    async def acall(self, send: Callable[[], Awaitable[T]]) -> T:
        retry = 0
        while True:
            try:
                return await send()
            except _CANDIDATES as error:
                delay = self._wait_before_retry(error, retry)
                if delay is None:
                    raise
            await self.clock.async_sleep(delay)
            retry += 1

    def stream(self, open_stream: Callable[[], Iterable[T]]) -> Iterator[T]:
        """Iterate a stream, retrying it only until its first item arrives."""
        head, rest = self.call(lambda: _first(iter(open_stream())))
        yield from head
        yield from rest

    async def astream(self, open_stream: Callable[[], AsyncIterable[T]]) -> AsyncIterator[T]:
        """``stream`` for an async stream."""
        head, rest = await self.acall(lambda: _afirst(aiter(open_stream())))
        for item in head:
            yield item
        async for item in rest:
            yield item

    def _wait_before_retry(self, error: Exception, retry: int) -> float | None:
        """Seconds to wait before retrying, or None to give up on ``error``."""
        reason = transient_reason(error)
        if reason is None or retry >= self.policy.max_retries:
            return None
        retry_after = retry_after_seconds(error, self.clock.now())
        delay = self.policy.delay(retry, retry_after, self.clock.uniform)
        # Never the prompt or the key: only what identifies the call (§6).
        logger.warning(
            "llm.retry provider=%s model=%s attempt=%d/%d reason=%s delay_s=%.2f",
            self.provider,
            self.model,
            retry + 1,
            self.policy.max_retries + 1,
            reason,
            delay,
        )
        return delay


def _first(items: Iterator[T]) -> tuple[list[T], Iterator[T]]:
    """Read one item ahead: a failure before it has produced nothing yet."""
    try:
        return [next(items)], items
    except StopIteration:
        return [], items


async def _afirst(items: AsyncIterator[T]) -> tuple[list[T], AsyncIterator[T]]:
    try:
        return [await anext(items)], items
    except StopAsyncIteration:
        return [], items

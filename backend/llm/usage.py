"""What model calls use and cost, counted as they happen.

A ``UsageCallback`` rides on a LangChain chat model (``metered``): it reads the
token counts of every call's answer (``usage_metadata``), prices the call, and
tells a ``UsageMeter`` before and after each one, so a caller can add spending
up while it happens and refuse a call that would go past a limit.

Where a call's cost comes from (``COST_SOURCES``, the first that knows wins):

1. what the provider says it charged: OpenRouter returns ``usage.cost`` (USD)
   on every answer, which LangChain hands on as ``response_metadata["cost"]``;
2. the model's published prices in the catalogue (``ModelInfo.price``);
3. otherwise the cost is unknown (None) and only the tokens are counted.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler, BaseCallbackManager
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from llm.catalog import ModelInfo


def _add_costs(first: float | None, second: float | None) -> float | None:
    if first is None:
        return second
    if second is None:
        return first
    return first + second


@dataclass(frozen=True)
class TokenUsage:
    """Tokens and cost of one or more model calls (§7 Value Object)."""

    input_tokens: int = 0
    output_tokens: int = 0
    #: USD: the known costs added up; None when no cost is known.
    cost_usd: float | None = None
    #: False once some tokens came from a call whose cost is unknown, which
    #: ``cost_usd`` then leaves out.
    cost_complete: bool = True

    @classmethod
    def of(cls, input_tokens: int, output_tokens: int, cost_usd: float | None) -> TokenUsage:
        """Counted tokens and their cost; an unknown cost of used tokens is incomplete."""
        used = input_tokens + output_tokens > 0
        return cls(input_tokens, output_tokens, cost_usd, cost_usd is not None or not used)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            _add_costs(self.cost_usd, other.cost_usd),
            self.cost_complete and other.cost_complete,
        )


NO_USAGE = TokenUsage()


def total(usages: Iterable[TokenUsage]) -> TokenUsage:
    return sum(usages, NO_USAGE)


CostSource = Callable[[AIMessage, TokenUsage, ModelInfo | None], float | None]


def _reported_cost(message: AIMessage, tokens: TokenUsage, model: ModelInfo | None) -> float | None:
    """What the provider says the call cost (OpenRouter's ``usage.cost``)."""
    cost = message.response_metadata.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return None
    return float(cost) if math.isfinite(cost) and cost >= 0 else None


def _catalogue_cost(message: AIMessage, tokens: TokenUsage, model: ModelInfo | None) -> float | None:
    """The call's tokens at the model's published prices."""
    return model.price(tokens.input_tokens, tokens.output_tokens) if model else None


#: Where a call's cost comes from, best first (Strategy chain, §5 O).
COST_SOURCES: tuple[CostSource, ...] = (_reported_cost, _catalogue_cost)


def _known_cost(message: AIMessage, tokens: TokenUsage, model: ModelInfo | None) -> float | None:
    for source in COST_SOURCES:
        cost = source(message, tokens, model)
        if cost is not None:
            return cost
    return None


def call_usage(message: AIMessage, model: ModelInfo | None) -> TokenUsage:
    """The tokens one answer used and, when it can be known, what it cost."""
    metadata = message.usage_metadata
    if metadata is None:
        # The provider sent no usage: there is nothing to count or price.
        return NO_USAGE
    tokens = TokenUsage(metadata.get("input_tokens", 0), metadata.get("output_tokens", 0))
    cost = _known_cost(message, tokens, model)
    return TokenUsage.of(tokens.input_tokens, tokens.output_tokens, cost)


def response_usage(response: LLMResult, model: ModelInfo | None) -> TokenUsage:
    """One call's usage: each prompt's first answer carries it (every other choice
    of the same prompt repeats it, so counting them all would count it twice)."""
    answers = [generations[0] for generations in response.generations if generations]
    return total(
        call_usage(answer.message, model)
        for answer in answers
        if isinstance(answer, ChatGeneration) and isinstance(answer.message, AIMessage)
    )


class UsageMeter(Protocol):
    """Hears about each model call of one agent (Observer port)."""

    def before_call(self) -> None:
        """Called before a call is sent; raising refuses it."""

    def after_call(self, usage: TokenUsage) -> None:
        """Called with what a finished call used."""


class _Unmetered:
    """Null Object: nobody counts these calls."""

    def before_call(self) -> None:
        return None

    def after_call(self, usage: TokenUsage) -> None:
        return None


UNMETERED: UsageMeter = _Unmetered()


class UsageCallback(BaseCallbackHandler):
    """Adds up what every call of one chat model uses, and tells a ``UsageMeter``.

    It runs inline and lets errors through (``raise_error``), so a meter that
    refuses a call stops the agent with the meter's own exception.
    """

    raise_error = True
    run_inline = True

    def __init__(self, model: ModelInfo | None, meter: UsageMeter = UNMETERED) -> None:
        super().__init__()
        self._model = model
        self._meter = meter
        self._lock = threading.Lock()
        self._total = NO_USAGE

    @property
    def total(self) -> TokenUsage:
        with self._lock:
            return self._total

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._meter.before_call()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        usage = response_usage(response, self._model)
        with self._lock:
            self._total += usage
        self._meter.after_call(usage)


def metered(model: BaseChatModel, callback: BaseCallbackHandler) -> BaseChatModel:
    """A copy of ``model`` whose every call ``callback`` hears (its own callbacks kept).

    The callback rides on the model, not on the agent's run config: on Python
    3.10 LangGraph cannot carry a config's callbacks into an async agent's
    model call, so they would never fire.
    """
    existing = model.callbacks
    if isinstance(existing, BaseCallbackManager):
        handlers = list(existing.handlers)
    else:
        handlers = list(existing or [])
    return model.model_copy(update={"callbacks": [*handlers, callback]})

"""Model metadata. The catalogue is the single source of truth for which model
ids the application accepts (AGENTS.md §3); the API exposes it over HTTP so the
client never keeps its own copy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    """Immutable description of one hosted model (§7 Value Object)."""

    provider: str
    model_id: str
    context_window: int | None = None
    supports_tools: bool = False
    supports_reasoning: bool = False
    supports_vision: bool = False
    fast: bool = False
    free: bool = False
    description: str = ""


class ModelCatalog:
    """Shared lookup behaviour for the per-provider catalogues below.

    ``cls.__dict__`` resolves to the concrete subclass, so each catalogue lists
    only its own models while the traversal logic is defined once (§3).
    """

    @classmethod
    def all(cls) -> dict[str, ModelInfo]:
        return {name: value for name, value in cls.__dict__.items() if isinstance(value, ModelInfo)}

    @classmethod
    def ids(cls) -> list[str]:
        return [model.model_id for model in cls.all().values()]

    @classmethod
    def by_id(cls, model_id: str) -> ModelInfo | None:
        return next((model for model in cls.all().values() if model.model_id == model_id), None)

    @classmethod
    def free_models(cls) -> list[ModelInfo]:
        return [model for model in cls.all().values() if model.free]

    @classmethod
    def fast_models(cls) -> list[ModelInfo]:
        return [model for model in cls.all().values() if model.fast]


class TogetherAIModels(ModelCatalog):
    """TogetherAI hosted models."""

    Kimi_K2_Thinking = ModelInfo(
        provider="togetherai",
        model_id="moonshotai/Kimi-K2-Thinking",
        supports_reasoning=True,
        description="Advanced reasoning and chain-of-thought model.",
    )
    Qwen3_Coder_480B_A35B = ModelInfo(
        provider="togetherai",
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        supports_tools=True,
        description="Massive coding-focused Qwen model.",
    )
    GPT_OSS_120B = ModelInfo(
        provider="togetherai",
        model_id="openai/gpt-oss-120b",
        supports_tools=True,
        supports_reasoning=True,
        description="Open-weight GPT-style 120B model.",
    )
    Llama4_Maverick_17B_128E = ModelInfo(
        provider="togetherai",
        model_id="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        supports_tools=True,
        description="Llama 4 Maverick instruction-tuned model.",
    )


class OpenRouterModels(ModelCatalog):
    """Models reachable through OpenRouter."""

    Qwen3_Coder_480B_A35B = ModelInfo(
        provider="openrouter",
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        supports_tools=True,
        description="High-end coding and agentic model.",
    )
    GPT_OSS_120B = ModelInfo(
        provider="openrouter",
        model_id="openai/gpt-oss-120b",
        supports_reasoning=True,
        supports_tools=True,
        description="Large open GPT-style model.",
    )
    Llama4_Maverick_17B_128E = ModelInfo(
        provider="openrouter",
        model_id="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        supports_tools=True,
        description="Efficient Llama 4 instruction model.",
    )
    GROK_4_1_FAST = ModelInfo(
        provider="openrouter",
        model_id="x-ai/grok-4.1-fast",
        fast=True,
        supports_tools=True,
        description="Fast Grok inference model.",
    )
    Qwen3_5_Plus = ModelInfo(
        provider="openrouter",
        model_id="qwen/qwen3.5-plus-02-15",
        supports_reasoning=True,
        supports_tools=True,
        description="Qwen 3.5 flagship model.",
    )
    GLM_5 = ModelInfo(
        provider="openrouter",
        model_id="z-ai/glm-5",
        supports_tools=True,
        description="GLM-5 multilingual reasoning model.",
    )
    Minimax_M2_5 = ModelInfo(
        provider="openrouter",
        model_id="minimax/minimax-m2.5",
        fast=True,
        description="Fast multimodal Minimax model.",
    )
    DeepSeek_V4_Flash = ModelInfo(
        provider="openrouter",
        model_id="deepseek/deepseek-v4-flash",
        fast=True,
        supports_tools=True,
        description="Ultra-fast DeepSeek inference model.",
    )
    Tencent_HY3_Preview = ModelInfo(
        provider="openrouter",
        model_id="tencent/hy3-preview",
        description="Tencent experimental preview model.",
    )
    Nemotron_3_Super_120B_Free = ModelInfo(
        provider="openrouter",
        model_id="nvidia/nemotron-3-super-120b-a12b:free",
        free=True,
        supports_reasoning=True,
        description="Free NVIDIA Nemotron model.",
    )


CATALOGS: dict[str, type[ModelCatalog]] = {
    "openrouter": OpenRouterModels,
    "togetherai": TogetherAIModels,
}


def catalog_for(provider: str) -> type[ModelCatalog]:
    """Return the catalogue for a provider name, or raise KeyError."""
    return CATALOGS[provider]

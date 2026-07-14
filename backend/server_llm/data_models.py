# data_models.py

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model_id: str
    context_window: Optional[int] = None
    supports_tools: bool = False
    supports_reasoning: bool = False
    supports_vision: bool = False
    fast: bool = False
    free: bool = False
    description: str = ""


class LLMTogetherAI:
    """
    TogetherAI hosted models.
    """

    Kimi_K2_Thinking = ModelInfo(
        provider="TogetherAI",
        model_id="moonshotai/Kimi-K2-Thinking",
        supports_reasoning=True,
        description="Advanced reasoning and chain-of-thought model.",
    )

    Qwen3_Coder_480B_A35B = ModelInfo(
        provider="TogetherAI",
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        supports_tools=True,
        description="Massive coding-focused Qwen model.",
    )

    GPT_OSS_120B = ModelInfo(
        provider="TogetherAI",
        model_id="openai/gpt-oss-120b",
        supports_tools=True,
        supports_reasoning=True,
        description="Open-weight GPT-style 120B model.",
    )

    Llama4_Maverick_17B_128E = ModelInfo(
        provider="TogetherAI",
        model_id="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        supports_tools=True,
        description="Llama 4 Maverick instruction-tuned model.",
    )

    @classmethod
    def all(cls) -> Dict[str, ModelInfo]:
        return {
            name: value
            for name, value in cls.__dict__.items()
            if isinstance(value, ModelInfo)
        }

    @classmethod
    def ids(cls) -> List[str]:
        return [model.model_id for model in cls.all().values()]


class OpenRouterLLM:
    """
    OpenRouter available models.
    """

    Qwen3_Coder_480B_A35B = ModelInfo(
        provider="OpenRouter",
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        supports_tools=True,
        description="High-end coding and agentic workflows.",
    )

    GPT_OSS_120B = ModelInfo(
        provider="OpenRouter",
        model_id="openai/gpt-oss-120b",
        supports_reasoning=True,
        supports_tools=True,
        description="Large open GPT-style model.",
    )

    Llama4_Maverick_17B_128E = ModelInfo(
        provider="OpenRouter",
        model_id="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        supports_tools=True,
        description="Efficient Llama 4 instruction model.",
    )

    GROK_4_1_FAST = ModelInfo(
        provider="OpenRouter",
        model_id="x-ai/grok-4.1-fast",
        fast=True,
        supports_tools=True,
        description="Fast Grok inference model.",
    )

    Qwen3_5_Plus_02_15 = ModelInfo(
        provider="OpenRouter",
        model_id="qwen/qwen3.5-plus-02-15",
        supports_reasoning=True,
        supports_tools=True,
        description="Qwen 3.5 flagship model.",
    )

    GLM_5 = ModelInfo(
        provider="OpenRouter",
        model_id="z-ai/glm-5",
        supports_tools=True,
        description="GLM-5 multilingual reasoning model.",
    )

    Minimax_M2_5 = ModelInfo(
        provider="OpenRouter",
        model_id="minimax/minimax-m2.5",
        fast=True,
        description="Fast multimodal Minimax model.",
    )

    DeepSeek_V4_Flash = ModelInfo(
        provider="OpenRouter",
        model_id="deepseek/deepseek-v4-flash",
        fast=True,
        supports_tools=True,
        description="Ultra-fast DeepSeek inference model.",
    )

    Tencent_HY3_Preview = ModelInfo(
        provider="OpenRouter",
        model_id="tencent/hy3-preview",
        description="Tencent experimental preview model.",
    )

    Nemotron_3_Super_120B_A12B_Free = ModelInfo(
        provider="OpenRouter",
        model_id="nvidia/nemotron-3-super-120b-a12b:free",
        free=True,
        supports_reasoning=True,
        description="Free NVIDIA Nemotron model.",
    )

    @classmethod
    def all(cls) -> Dict[str, ModelInfo]:
        return {
            name: value
            for name, value in cls.__dict__.items()
            if isinstance(value, ModelInfo)
        }

    @classmethod
    def ids(cls) -> List[str]:
        return [model.model_id for model in cls.all().values()]

    @classmethod
    def free_models(cls) -> List[ModelInfo]:
        return [
            model
            for model in cls.all().values()
            if model.free
        ]

    @classmethod
    def fast_models(cls) -> List[ModelInfo]:
        return [
            model
            for model in cls.all().values()
            if model.fast
        ]


# Optional unified registry

ALL_MODELS = {
    "together_ai": LLMTogetherAI.all(),
    "openrouter": OpenRouterLLM.all(),
}
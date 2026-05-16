import os
from pathlib import Path

from dotenv import load_dotenv

from server_llm.data_models import LLMTogetherAI, OpenRouterLLM
from server_llm.server_llm import OpenRouterServerLLM, TogetherAIsServerLLM

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_ai_service():
    """
    Initialize the configured LLM provider.

    LLM_PROVIDER accepts:
    - togetherai: TogetherAIsServerLLM, default
    - openrouter: OpenRouterServerLLM
    """
    provider = os.getenv("LLM_PROVIDER", "togetherai").strip().lower()

    if provider == "openrouter":
        api_key = os.getenv("OPEN_ROUTER_KEY")
        if not api_key or "your_api_key_here" in api_key:
            return None, None, "OPEN_ROUTER_KEY is missing or invalid in .env"
        try:
            return OpenRouterServerLLM(api_key_openrouter=api_key), OpenRouterLLM.Minimax_M2_5, None
        except Exception as exc:
            return None, None, str(exc)

    api_key = os.getenv("TOGAI_API_KEY")
    if not api_key or "your_api_key_here" in api_key:
        return None, None, "TOGAI_API_KEY is missing or invalid in .env"
    try:
        return TogetherAIsServerLLM(api_key_togai=api_key), LLMTogetherAI.Llama4_Maverick_17B_128E, None
    except Exception as exc:
        return None, None, str(exc)

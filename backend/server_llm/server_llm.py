from together import Together
from openai import OpenAI  # Required for OpenRouter
import logging
from .data_models import LLMTogetherAI, ModelInfo, OpenRouterLLM

DEFAULT_TOGETHER_MODEL = LLMTogetherAI.Llama4_Maverick_17B_128E
DEFAULT_OPENROUTER_MODEL = OpenRouterLLM.DeepSeek_V4_Flash


def resolve_model_id(llm):
    if isinstance(llm, ModelInfo):
        return llm.model_id
    if not llm:
        raise ValueError("LLM model id is required")
    return str(llm)


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),    # Save logs to file
        logging.StreamHandler()            # Show logs in console too
    ]
)


class TogetherAIsServerLLM:
    def __init__(self, api_key_togai):
        self.togai_api_key = api_key_togai
        if self.togai_api_key:
            self.client = Together(api_key=self.togai_api_key)
        else:
            raise ValueError("Please add a correct TOGETHERAI API KEY")

    def _generate_response_llm(self, prompt, llm):
        response = self.client.chat.completions.create(
            model=resolve_model_id(llm),
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        if response.choices:
            return response.choices[0].message.content
        return ""

    def generate_response(self, prompt, llm=DEFAULT_TOGETHER_MODEL):
        return self._generate_response_llm(prompt, llm)

    def generate_streaming_response(self, prompt, llm=DEFAULT_TOGETHER_MODEL):
        """
        Generates a streaming response from the TogetherAI API.
        """
        stream = self.client.chat.completions.create(
            model=resolve_model_id(llm),
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            stream=True
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class OpenRouterServerLLM:
    def __init__(self, api_key_openrouter):
        self.openrouter_api_key = api_key_openrouter
        if self.openrouter_api_key:
            # Initialize the OpenAI client with OpenRouter's base URL
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_api_key,
            )
        else:
            raise ValueError("Please add a correct OPENROUTER API KEY")

    def _generate_response_llm(self, prompt, llm):
        try:
            response = self.client.chat.completions.create(
                model=resolve_model_id(llm),
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            if response.choices:
                return response.choices[0].message.content
            return ""
        except Exception as e:
            logging.error(f"OpenRouter API error: {e}")
            return ""

    def generate_response(self, prompt, llm=DEFAULT_OPENROUTER_MODEL):
        return self._generate_response_llm(prompt, llm)

    def generate_streaming_response(self, prompt, llm=DEFAULT_OPENROUTER_MODEL):
        """
        Generates a streaming response from the OpenRouter API.
        """
        try:
            stream = self.client.chat.completions.create(
                model=resolve_model_id(llm),
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                stream=True
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f"OpenRouter streaming error: {e}")

from together import Together
from openai import OpenAI  # Required for OpenRouter
import logging
from data_models import LLMTogetherAI, OpenRouterLLM

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
            model=llm,
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

    def generate_response(self, prompt, llm=LLMTogetherAI.Llama4_Maverick_17B_128E):
        return self._generate_response_llm(prompt, llm)

    def generate_streaming_response(self, prompt, llm=LLMTogetherAI.Llama4_Maverick_17B_128E):
        """
        Generates a streaming response from the TogetherAI API.
        """
        stream = self.client.chat.completions.create(
            model=llm,
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
                model=llm,
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

    def generate_response(self, prompt, llm=OpenRouterLLM.Minimax_M2_5):
        return self._generate_response_llm(prompt, llm)

    def generate_streaming_response(self, prompt, llm=OpenRouterLLM.Minimax_M2_5):
        """
        Generates a streaming response from the OpenRouter API.
        """
        try:
            stream = self.client.chat.completions.create(
                model=llm,
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
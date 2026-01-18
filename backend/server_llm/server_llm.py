from together import Together
import logging


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
        return response.choices[0].message.content

    def generate_response(self, prompt, llm):
        return self._generate_response_llm(prompt, llm)

    def generate_streaming_response(self, prompt, llm):
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
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


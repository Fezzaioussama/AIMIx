import os
from server_llm import TogetherAIsServerLLM
from data_models import LLMTogetherAI
from dotenv import load_dotenv


load_dotenv(".env")


ai_service_togetherai = TogetherAIsServerLLM(api_key_togai=os.getenv('TOGAI_API_KEY'))

print(f"The llm used is: {LLMTogetherAI.GPT_OSS_120B}")
prompt_user = input("Enter You Question:\n")

print(ai_service_togetherai.generate_response(prompt=prompt_user, llm=LLMTogetherAI.GPT_OSS_120B))
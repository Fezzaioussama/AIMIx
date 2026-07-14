import json
import re

from server_llm.data_models import OpenRouterLLM

DEFAULT_PIPELINE_MODEL = OpenRouterLLM.DeepSeek_V4_Flash.model_id
AVAILABLE_MODELS = [
    DEFAULT_PIPELINE_MODEL,
    *[
        model_id
        for model_id in OpenRouterLLM.ids()
        if model_id != DEFAULT_PIPELINE_MODEL
    ],
]
AVAILABLE_MODELS_TEXT = ", ".join(AVAILABLE_MODELS)

PIPELINE_GENERATION_PROMPT = f"""You are an AI pipeline architect. Given a user's description of a workflow, generate a structured multi-step pipeline.

Each step should have:
1. A clear, specific prompt template that uses {{input}} as a placeholder for the previous step's output
2. A recommended model from this list: {AVAILABLE_MODELS_TEXT}

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{{
  "name": "Pipeline Name",
  "steps": [
    {{"order": 1, "prompt": "Your prompt with {{input}}", "model": "model-name"}},
    {{"order": 2, "prompt": "Next prompt with {{input}}", "model": "model-name"}}
  ]
}}

User's workflow description:
"""


def parse_generated_pipeline(response):
    json_match = re.search(r"\{[\s\S]*\}", response)
    if not json_match:
        return None, "Failed to parse pipeline structure from AI response"

    pipeline_data = json.loads(json_match.group())
    if "name" not in pipeline_data or "steps" not in pipeline_data:
        return None, "Invalid pipeline structure returned by AI"

    for step in pipeline_data["steps"]:
        if step.get("model") not in AVAILABLE_MODELS:
            step["model"] = AVAILABLE_MODELS[0]

    return pipeline_data, None

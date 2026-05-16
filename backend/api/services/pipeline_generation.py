import json
import re

AVAILABLE_MODELS = [
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
    "meta-llama/Llama-3-8b-chat-hf",
    "openai/gpt-oss-120b",
    "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
]

PIPELINE_GENERATION_PROMPT = """You are an AI pipeline architect. Given a user's description of a workflow, generate a structured multi-step pipeline.

Each step should have:
1. A clear, specific prompt template that uses {input} as a placeholder for the previous step's output
2. A recommended model from this list: meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8, meta-llama/Llama-3-8b-chat-hf, openai/gpt-oss-120b, Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{
  "name": "Pipeline Name",
  "steps": [
    {"order": 1, "prompt": "Your prompt with {input}", "model": "model-name"},
    {"order": 2, "prompt": "Next prompt with {input}", "model": "model-name"}
  ]
}

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

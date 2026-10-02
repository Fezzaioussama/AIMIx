"""Prompt templates. Kept apart from transport and persistence so a service that
builds a prompt does not also perform the call (AGENTS.md §5 S)."""

from __future__ import annotations

from api.services.agent_types import ToolDescriptor

PIPELINE_GENERATION_TEMPLATE = """You are an AI pipeline architect. Given a user's \
description of a workflow, generate a structured multi-step pipeline.

Each step runs as an agent. These tools are currently available to its user:
{tools}

Give each step a role, a focused goal, and only the tools needed for that goal.
Use exact tool names from the list. Use [] when a step needs no tools, or null
to make all available tools accessible. A step's prompt should say when to use
its tools and what result to deliver.

Each step should have:
1. A clear, specific prompt template that uses {{input}} as a placeholder for the \
previous stage's output
2. A recommended model from this list: {models}
3. A unique "order" (1, 2, 3, ...) and a "stage" number
4. A short "title" of 2-4 words naming what the step produces, e.g. "Tweet draft"
5. "is_output": true if its result is something the user asked to receive, \
false if it is intermediate work that only feeds later steps
6. A short "role" describing the agent's specialty and "allowed_tools" as a
list of exact names, [], or null

Steps can run sequentially or in parallel:
- Stages run one after another, in ascending order.
- Steps that share a stage run in parallel on the same input. Use this for \
independent work on the same text, e.g. several analyses, translations or drafts.
- A step in a later stage receives the previous stage's output as {{input}}. When \
that stage had several steps, their outputs are joined, each under a \
"{heading}" heading.
- If the user wants one combined answer after parallel steps, end with a single \
step in its own stage that merges them.
- A pipeline can have several outputs, from any stage: mark every deliverable the \
user will want to read (e.g. each of several drafts, plus a final pick). Output \
steps still feed the next stage.
- When the request names several deliverables, create a separate output step for \
each one. Group independent deliverables in the same stage so they can run in \
parallel; add a later synthesis stage only if the request calls for one.

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{{
  "name": "Pipeline Name",
  "steps": [
    {{"order": 1, "stage": 1, "title": "Key facts", "role": "Researcher", \
"allowed_tools": [], "is_output": false, "prompt": "Your prompt with {{input}}", \
"model": "model-name"}},
    {{"order": 2, "stage": 2, "title": "Tweet draft", "role": "Writer", \
"allowed_tools": [], "is_output": true, "prompt": "A prompt with {{input}}", \
"model": "model-name"}},
    {{"order": 3, "stage": 2, "title": "Email draft", "role": "Writer", \
"allowed_tools": [], "is_output": true, "prompt": "A parallel prompt with {{input}}", \
"model": "model-name"}},
    {{"order": 4, "stage": 3, "title": "Best pick", "role": "Editor", \
"allowed_tools": [], "is_output": true, "prompt": "Pick the best of these: {{input}}", \
"model": "model-name"}}
  ]
}}

User's workflow description:
"""

PARALLEL_OUTPUT_HEADING = "## Output of step {order}"


def pipeline_generation_prompt(
    description: str, available_models: list[str], tools: list[ToolDescriptor] | None = None
) -> str:
    """Render the planner prompt for a workflow description."""
    tool_lines = [f"- {item.name} ({item.source}): {item.description}" for item in tools or []]
    header = PIPELINE_GENERATION_TEMPLATE.format(
        models=", ".join(available_models),
        heading=PARALLEL_OUTPUT_HEADING.format(order="N"),
        tools="\n".join(tool_lines) if tool_lines else "No tools are configured.",
    )
    return f"{header}{description}"


def step_prompt(template: str, current_input: str) -> str:
    """Substitute the running value into a step template.

    ``{input}`` is replaced where present; otherwise the value is appended, so a
    template without the placeholder still receives its input.
    """
    if "{input}" in template:
        return template.replace("{input}", current_input)
    return f"{template}\n\nInput: {current_input}"


def merge_stage_outputs(outputs: list[tuple[int, str]]) -> str:
    """Turn one stage's ``(step order, output)`` pairs into the next stage's input.

    A single step passes its output through unchanged, so a sequential pipeline
    behaves exactly as before; parallel outputs are labelled by step so the next
    prompt can tell them apart.
    """
    if len(outputs) == 1:
        return outputs[0][1]
    return "\n\n".join(
        f"{PARALLEL_OUTPUT_HEADING.format(order=order)}\n\n{output}" for order, output in outputs
    )

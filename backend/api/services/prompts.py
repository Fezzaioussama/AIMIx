"""Prompt templates. Kept apart from transport and persistence so a service that
builds a prompt does not also perform the call (AGENTS.md §5 S)."""

from __future__ import annotations

import re
from collections.abc import Mapping

from api.models import PIPELINE_INPUT_NAME_PATTERN, RESERVED_INPUT_NAME
from api.services.agent_types import ToolDescriptor

PIPELINE_GENERATION_TEMPLATE = """You are an AI pipeline architect. Given a user's \
description of a workflow, generate a structured multi-step pipeline.

Each step runs as an agent. These tools are currently available to its user:
{tools}

Give each step a role, a focused goal, and only the tools needed for that goal.
A step that needs current facts, sources, exact numbers or today's date should get \
the matching tools from the list rather than rely on the model's memory.
Use exact tool names from the list. Use [] when a step needs no tools, or null
to make all available tools accessible. A step's prompt should say when to use
its tools and what result to deliver.

The pipeline's inputs are what the user fills in each time it runs. List them in \
"inputs", one for each distinct piece of information the workflow needs (e.g. a \
topic and an audience), each with:
- "name": a snake_case identifier (lowercase letters, digits and underscores, \
starting with a letter), never "input"
- "label": a short label for the run form, e.g. "Target audience"
- "description": one sentence telling the user what to enter
Any step's prompt, in any stage, inserts an input's value with {{name}}, e.g. \
{{topic}}, so later steps still see the original request. Use [] only when the \
workflow takes one free-form text.

Each step should have:
1. A clear, specific prompt template. {{input}} stands for the previous stage's \
output; in the first stage it holds the run's inputs. Insert named inputs as {{name}}.
2. A recommended model from this list: {models}
3. A unique "order" (1, 2, 3, ...) and a "stage" number
4. A short "title" of 2-4 words naming what the step produces, e.g. "Tweet draft"
5. "expected_output": one sentence describing the content and format of the \
step's result, e.g. "A tweet under 280 characters ending with two hashtags"
6. "is_output": true if its result is something the user asked to receive, \
false if it is intermediate work that only feeds later steps
7. A short "role" describing the agent's specialty and "allowed_tools" as a
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
  "inputs": [
    {{"name": "topic", "label": "Topic", "description": "What the posts are about"}}
  ],
  "steps": [
    {{"order": 1, "stage": 1, "title": "Key facts", "role": "Researcher", \
"allowed_tools": [], "is_output": false, "expected_output": "A bullet list of key facts", \
"prompt": "List key facts about {{topic}}", "model": "model-name"}},
    {{"order": 2, "stage": 2, "title": "Tweet draft", "role": "Writer", \
"allowed_tools": [], "is_output": true, "expected_output": "One tweet under 280 characters", \
"prompt": "Write a tweet about {{topic}} from these facts: {{input}}", "model": "model-name"}},
    {{"order": 3, "stage": 2, "title": "Email draft", "role": "Writer", \
"allowed_tools": [], "is_output": true, "expected_output": "A short email with a subject line", \
"prompt": "Write an email about {{topic}} from these facts: {{input}}", "model": "model-name"}},
    {{"order": 4, "stage": 3, "title": "Best pick", "role": "Editor", \
"allowed_tools": [], "is_output": true, "expected_output": "The better draft and why", \
"prompt": "Pick the best of these: {{input}}", "model": "model-name"}}
  ]
}}

User's workflow description:
"""

PARALLEL_OUTPUT_HEADING = "## Output of step {order}"
INPUT_HEADING = "## {label}"

#: ``{name}`` tokens a step template may hold; only names a run fills are replaced.
PLACEHOLDER = re.compile(rf"\{{({PIPELINE_INPUT_NAME_PATTERN})\}}")

STEP_AGENT_TEMPLATE = (
    "You are {identity} in an AIMIx pipeline. Your final reply is handed on as the "
    "result of this step, so make it the complete deliverable, without remarks about "
    "your process."
)
STEP_AGENT_OUTPUT_TEMPLATE = (
    "Your final reply must match this expected output in content and format: {expected_output}"
)
STEP_AGENT_TOOL_GUIDANCE = (
    "Use your tools whenever the task depends on something you cannot be sure of, such "
    "as current events, figures, calculations or the content of a web page, instead of "
    "guessing. Cite the URL of every web source you rely on. When a tool returns an "
    "error, adapt: try another query or source, or say what could not be verified."
)


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


def step_agent_system_prompt(role: str, has_tools: bool, expected_output: str = "") -> str:
    """The system prompt for one step's agent: its identity, the result it must
    deliver when the step names one, and tool guidance only when it has tools."""
    identity = f"the {role} agent" if role else "an agent"
    parts = [STEP_AGENT_TEMPLATE.format(identity=identity)]
    if expected_output.strip():
        parts.append(STEP_AGENT_OUTPUT_TEMPLATE.format(expected_output=expected_output.strip()))
    if has_tools:
        parts.append(STEP_AGENT_TOOL_GUIDANCE)
    return "\n\n".join(parts)


def step_prompt(
    template: str,
    current_input: str,
    values: Mapping[str, str] | None = None,
    *,
    first_stage: bool = False,
) -> str:
    """Fill a step template from its stage's input and the run's named inputs.

    ``{input}`` takes the stage's input and ``{name}`` the named input ``name``,
    in one pass, so substituted text is never expanded again; other braces stay
    as written. A template that does not place its stage's input gets it
    appended. In the first stage, whose input is the named inputs themselves,
    using any of them counts as placing it.
    """
    fills = {**(values or {}), RESERVED_INPUT_NAME: current_input}
    used: set[str] = set()

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in fills:
            return match.group(0)
        used.add(name)
        return fills[name]

    prompt = PLACEHOLDER.sub(fill, template)
    placed = RESERVED_INPUT_NAME in used or (first_stage and bool(used))
    return prompt if placed else f"{prompt}\n\nInput: {current_input}"


def _join_sections(sections: list[tuple[str, str]]) -> str:
    """A single section passes through unchanged; several are joined, each under
    its heading, so the prompt receiving them can tell them apart."""
    if len(sections) == 1:
        return sections[0][1]
    return "\n\n".join(f"{heading}\n\n{body}" for heading, body in sections)


def merge_stage_outputs(outputs: list[tuple[int, str]]) -> str:
    """Turn one stage's ``(step order, output)`` pairs into the next stage's input.

    A single step passes its output through unchanged, so a sequential pipeline
    behaves exactly as before; parallel outputs are labelled by step.
    """
    return _join_sections(
        [(PARALLEL_OUTPUT_HEADING.format(order=order), output) for order, output in outputs]
    )


def merge_input_values(values: list[tuple[str, str]]) -> str:
    """Turn a run's ``(label, value)`` pairs into the first stage's input: one
    value passes through unchanged, several are labelled."""
    return _join_sections([(INPUT_HEADING.format(label=label), value) for label, value in values])

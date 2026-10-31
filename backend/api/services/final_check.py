"""The final check every new pipeline ends with (§5 S). The planner is asked to add
it (``flow_prompts.FINAL_REVIEW_GUIDE``) and writes it best, in the language of the
request; when its plan holds no reviewer at all, ``with_final_check`` adds one, so
every new team has the check whatever the model did."""

from __future__ import annotations

from typing import Any

from api.services.flow_prompts import (
    FINAL_CHECK_EXPECTED_OUTPUT,
    FINAL_CHECK_INTRO,
    FINAL_CHECK_TASK,
    FINAL_CHECK_TITLE,
)
from api.services.plan_questions import Answer

#: How many times the added check may send the work back.
FINAL_CHECK_ROUNDS = 2
FINAL_CHECK_ROLE = "Orchestrator"
#: The request is quoted in the check's prompt, cut to this many characters.
FINAL_CHECK_REQUEST_MAX_CHARS = 20_000


def _quoted(description: str, answers: tuple[Answer, ...]) -> str:
    """The request as plain text: the description and the answers to the planner's
    questions, with braces made round so none of it can act as a placeholder."""
    pairs = [f"Q: {item.question}\nA: {item.answer}" for item in answers]
    text = "\n\n".join([description.strip(), *pairs])[:FINAL_CHECK_REQUEST_MAX_CHARS]
    return text.replace("{", "(").replace("}", ")")


def with_final_check(
    plan: dict[str, Any], description: str, answers: tuple[Answer, ...], model: str
) -> None:
    """Add a last stage with an orchestrator that checks the work against the request
    and sends it back to the earliest stage making a deliverable, unless the plan (a
    sanitised one, see ``parse_plan``) already has a reviewer."""
    steps: list[dict[str, Any]] = plan["steps"]
    if any(step["review"] for step in steps):
        return
    made = [step["stage"] for step in steps if step["is_output"]] or [steps[0]["stage"]]
    request = _quoted(description, answers)
    steps.append(
        {
            "order": len(steps) + 1,
            "stage": max(step["stage"] for step in steps) + 1,
            "title": FINAL_CHECK_TITLE,
            "role": FINAL_CHECK_ROLE,
            "prompt": f"{FINAL_CHECK_INTRO}\n\n{request}\n\n{FINAL_CHECK_TASK}",
            "model": model,
            "allowed_tools": [],
            "is_output": False,
            "expected_output": FINAL_CHECK_EXPECTED_OUTPUT,
            "condition": None,
            "review": {"send_back_to_stage": min(made), "max_rounds": FINAL_CHECK_ROUNDS},
        }
    )

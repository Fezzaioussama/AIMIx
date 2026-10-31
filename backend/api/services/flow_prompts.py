"""Prompt text for conditional steps and review loops (§5 S, Builder).

Kept beside ``prompts.py`` so that module stays about the steps themselves: the
planner is told about the two optional step fields here, and a reviewer and the
steps it sends work back to are told what they need to know. Text that goes
through ``str.format`` (the planner guide) doubles its literal braces.
"""

from __future__ import annotations

from api.models import FEEDBACK_PLACEHOLDER, STEP_CONDITION_VALUE_MAX_LENGTH, STEP_REVIEW_MAX_ROUNDS

#: Added to the planner's guide for generation and revision alike (§3).
FLOW_PLANNER_GUIDE = f"""\
Two optional step fields change how the work flows. Leave them out (or null) unless the \
request asks for them, for example "only if ..." or "send it back ...".
- "condition": run the step only when something is true; otherwise it is skipped. For \
example {{{{"source": "previous_output", "operator": "contains", "value": "blog"}}}}. \
"source" is "previous_output" (the {{{{input}}}} text), "input:<name>" (one of the \
pipeline's inputs) or "step:<order>" (the result of a step in an earlier stage). \
"operator" is contains, not_contains, equals, not_equals, is_empty or not_empty (the last \
two take no "value"). Text is compared ignoring case and surrounding spaces; "value" has at \
most {STEP_CONDITION_VALUE_MAX_LENGTH} characters. A stage whose steps are all skipped \
hands its input on unchanged.
- "review": make the step a reviewer that can send the work back for fixes. For example \
{{{{"send_back_to_stage": 2, "max_rounds": 2}}}}. When the reviewer says the work needs \
fixes, the stages from that earlier stage up to the reviewer's own run again, at most \
max_rounds (1 to {STEP_REVIEW_MAX_ROUNDS}) times; the steps of the stage it goes back to \
also get the reviewer's feedback, which a prompt can place with \
{{{{{FEEDBACK_PLACEHOLDER}}}}}. The reviewer's stage must come after send_back_to_stage, and \
two review loops must not share a stage. A reviewer's prompt should judge the work it is \
given ({{{{input}}}}) and say what to fix; AIMIx itself asks it to end with a verdict line, so \
never write that in the prompt. A reviewer's own answer is feedback: mark the step whose \
work it reviews as the output (is_output), not the reviewer. A stage after the reviewer \
receives only the reviewer's answer, so then ask the reviewer to repeat the approved work \
in full.

"""

#: Added to the planner's revision rules.
FLOW_REVISION_RULES = f"""\
- Copy each step's condition and review exactly as they are unless the change request is \
about them (to remove one, set it to null). A condition may only look at the pipeline's \
inputs, the previous result and steps in earlier stages; a review's send_back_to_stage \
must be an earlier stage than the reviewer's. When you renumber steps or stages, update \
every "step:<order>" source and every send_back_to_stage to match. \
{{{{{FEEDBACK_PLACEHOLDER}}}}} is always a valid placeholder.
"""

#: Only a new pipeline gets it (``plan_prompts``): a revision changes only what it is
#: asked to. It is appended after ``str.format``, so its braces are literal.
FINAL_REVIEW_GUIDE = """
Every new pipeline ends with a check by an orchestrator, unless the description asks for \
none or the pipeline already has a reviewer. Add one last stage holding a single step with \
the role "Orchestrator", is_output false and no tools, and a "review" that sends the work \
back to the stage that makes the deliverables (the earliest one, when several do), with \
max_rounds 2. Its prompt asks it to check the work it is given ({input}) against the \
user's request: every deliverable present, complete, correct and in the format asked for, \
and to say exactly what to fix. Keep is_output on the steps whose work it checks.

"""

#: What a reviewer's system prompt adds: judge the work, and end with the verdict line.
REVIEWER_RULE = (
    "You are reviewing the work you are given. Say what is good and what must be fixed, "
    "then end your reply with one final line that holds only 'VERDICT: PASS' when the "
    "work is good enough, or only 'VERDICT: REVISE' when it needs fixes."
)

#: What the steps a reviewer sent work back to are told, unless their own prompt
#: places the feedback with ``{feedback}``.
FEEDBACK_BLOCK = (
    "Feedback from the reviewer (round {round} of {rounds}):\n\n{feedback}\n\n"
    "Revise your work to fix what the reviewer found."
)
#: In place of feedback text when a reviewer asked for another round without saying why.
NO_FEEDBACK_DETAIL = "The reviewer asked for another round but gave no details."

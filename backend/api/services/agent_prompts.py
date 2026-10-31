"""What a pipeline step's agent is told before its task (§5 S, Builder): who it is, how to
work, its team and this run, the result it owes, and how to use tools or give a verdict.
Kept apart from the planner's prompts (``prompts``), which decide what each step does."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from api.services.flow_prompts import REVIEWER_RULE

STEP_AGENT_TEMPLATE = (
    "You are {identity} in an AIMIx pipeline. Your final reply is handed on as the "
    "result of this step, so make it the complete deliverable, without remarks about "
    "your process."
)
#: Every agent's working rules: the faults seen most in real runs (duplicated work,
#: preambles, a note that a file was saved instead of the work, invented facts, refusals).
STEP_AGENT_WORK_RULES = (
    "How to work:\n"
    "- Do your own part only; the rest of the team covers theirs.\n"
    "- Write the deliverable itself, complete and specific to this request, in the "
    "language of the request. Use Markdown headings, lists and tables when they help. "
    'No preamble such as "Here is", and no notes about the team or your process.\n'
    "- If you save a file, your reply still holds the full deliverable.\n"
    "- Never invent facts, sources, quotes, links or tool results. When you cannot check "
    "a fact, figure or price, give your best knowledge and mark it as an estimate to verify.\n"
    "- Do not refuse: if part of the task cannot be done, do the rest and say in one line "
    "what is missing."
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
#: How much of each run input every agent is shown in its brief; its task holds the rest.
BRIEF_VALUE_MAX_CHARS = 600


@dataclass(frozen=True)
class AgentRole:
    """Who a step's agent is (§7 Value Object): its role, the result it owes, whether
    it reviews the work, and what it is told about its team (``team_brief``)."""

    role: str
    expected_output: str = ""
    reviewer: bool = False
    context: str = ""


@dataclass(frozen=True)
class TeamMember:
    order: int
    stage: int
    role: str
    title: str


@dataclass(frozen=True)
class TeamView:
    """What every agent of a run is told about it: the team, the day, and the values
    the person gave as ``(label, value)`` pairs."""

    name: str
    members: tuple[TeamMember, ...]
    inputs: tuple[tuple[str, str], ...] = ()
    today: date | None = None


def _member_line(member: TeamMember, own_order: int) -> str:
    makes = f": {member.title}" if member.title else ""
    you = " (you)" if member.order == own_order else ""
    return f"- Stage {member.stage}, {member.role or 'Agent'}{makes}{you}"


def _shortened(value: str) -> str:
    text = value.strip()
    if len(text) <= BRIEF_VALUE_MAX_CHARS:
        return text
    return f"{text[:BRIEF_VALUE_MAX_CHARS].rstrip()}… (the rest is in your task when you need it)"


def team_brief(team: TeamView, own_order: int) -> str:
    """The team as one step's agent sees it: every member in the order they work, itself
    marked, then today's date and what the person gave for this run."""
    lines = [
        f'You work in the team "{team.name}". Its agents, by stage (a stage\'s agents '
        "work at the same time; later stages get earlier stages' results):",
        *(_member_line(member, own_order) for member in team.members),
    ]
    if team.today is not None:
        lines.append(f"Today's date is {team.today:%A %d %B %Y}.")
    if team.inputs:
        lines.append("What the person gave for this run:")
        lines.extend(f"- {label}: {_shortened(value)}" for label, value in team.inputs)
    return "\n".join(lines)


def step_agent_system_prompt(agent: AgentRole, has_tools: bool) -> str:
    """The system prompt for one step's agent: its identity, the working rules, its team
    and this run when known, the result it must deliver when the step names one, tool
    guidance only when it has tools, and, for a reviewer, the rule to end with a verdict
    line."""
    identity = f"the {agent.role} agent" if agent.role else "an agent"
    parts = [STEP_AGENT_TEMPLATE.format(identity=identity), STEP_AGENT_WORK_RULES]
    if agent.context.strip():
        parts.append(agent.context.strip())
    if agent.expected_output.strip():
        expected = agent.expected_output.strip()
        parts.append(STEP_AGENT_OUTPUT_TEMPLATE.format(expected_output=expected))
    if has_tools:
        parts.append(STEP_AGENT_TOOL_GUIDANCE)
    if agent.reviewer:
        parts.append(REVIEWER_RULE)
    return "\n\n".join(parts)

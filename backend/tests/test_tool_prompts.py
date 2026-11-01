"""What agents are told about links: the web wording only for a step that can read the
web, the rule never to describe an unread page for every agent, and the planner told
to ask for a page's content in the run form instead of handing an agent a link."""

from __future__ import annotations

import pytest

from api.services.plan_prompts import PlanRequest, pipeline_generation_prompt
from api.services.prompts import pipeline_revision_prompt, step_agent_system_prompt
from api.services.tool_prompts import (
    LINKS_PLANNER_GUIDE,
    LINKS_RULE,
    STEP_AGENT_TOOL_GUIDANCE,
    STEP_AGENT_WEB_GUIDANCE,
)


def test_a_step_without_a_web_tool_is_not_told_about_web_pages() -> None:
    prompt = step_agent_system_prompt("Writer", ["calculator", "read_workspace_file"])

    assert STEP_AGENT_TOOL_GUIDANCE in prompt
    assert STEP_AGENT_WEB_GUIDANCE not in prompt
    assert "web" not in prompt and "URL" not in prompt


@pytest.mark.parametrize("web_tool", ["fetch_url", "web_search"])
def test_a_step_with_a_web_tool_is_told_to_cite_its_sources(web_tool: str) -> None:
    prompt = step_agent_system_prompt("Researcher", ["calculator", web_tool])

    assert STEP_AGENT_TOOL_GUIDANCE in prompt
    assert STEP_AGENT_WEB_GUIDANCE in prompt
    assert "cite the URL of every web source" in prompt


@pytest.mark.parametrize("tools", [[], ["calculator"], ["fetch_url"]])
def test_every_agent_is_told_it_cannot_open_links_on_its_own(tools: list[str]) -> None:
    prompt = step_agent_system_prompt("Writer", tools)

    assert LINKS_RULE in prompt
    assert "You cannot open links unless one of your tools can." in prompt
    assert "never describe or summarise a page you have not read" in prompt


def test_a_step_without_tools_gets_the_links_rule_and_no_tool_guidance() -> None:
    prompt = step_agent_system_prompt("", [])

    identity, links = prompt.split("\n\n")
    assert identity.startswith("You are an agent in an AIMIx pipeline.")
    assert links == LINKS_RULE


def test_the_guidance_comes_in_order_and_the_verdict_rule_last() -> None:
    prompt = step_agent_system_prompt("QA", ["fetch_url"], "A short critique", reviewer=True)

    parts = prompt.split("\n\n")
    assert parts[2:5] == [STEP_AGENT_TOOL_GUIDANCE, STEP_AGENT_WEB_GUIDANCE, LINKS_RULE]
    assert parts[1].endswith(": A short critique")
    assert parts[5].endswith("'VERDICT: REVISE' when it needs fixes.")


def test_the_planner_is_told_agents_cannot_open_links() -> None:
    generation = pipeline_generation_prompt(PlanRequest("Sum up https://example.com"), ["m"])
    revision = pipeline_revision_prompt({"name": "P", "steps": []}, "Add a summary", ["m"])

    for prompt in (generation, revision):
        assert LINKS_PLANNER_GUIDE in prompt
        assert "An agent cannot open a link unless one of its tools can." in prompt
        assert 'with "Attach a document" or "Add a web page"' in prompt

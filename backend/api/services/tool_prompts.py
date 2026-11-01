"""What a step agent is told about its tools and about links, and what the planner is
told about links (§5 S, Builder). An agent opens a page only through a tool that reads
the web, so only a step with one hears about web pages and citing URLs; every agent is
told never to describe a page it has not read, and the planner to ask the user for a
page's content instead of handing an agent a link."""

from __future__ import annotations

from collections.abc import Collection

from api.services.toolbox.registry import OUTBOUND_TOOLS
from api.services.toolbox.tools import SAVE_ARTIFACT

#: For a step with any tool.
STEP_AGENT_TOOL_GUIDANCE = (
    "Use your tools whenever the task depends on something you cannot be sure of, such "
    "as current events, figures or calculations, instead of guessing. When a tool "
    "returns an error, adapt: try another query or source, or say what could not be "
    "verified."
)
#: Only for a step with a tool that reads the web (``OUTBOUND_TOOLS``).
STEP_AGENT_WEB_GUIDANCE = (
    "Your tools can read the web: use them for the content of a web page instead of "
    "guessing, and cite the URL of every web source you rely on."
)
#: Only for a step with save_artifact, which reports a PDF's page count.
STEP_AGENT_SAVE_GUIDANCE = (
    "When the request sets a length for a file (one page, two pages), check the page "
    "count save_artifact reports. If the file is longer, shorten the content and save it "
    "again under the same name: that replaces your draft."
)
#: For every agent, with or without tools.
LINKS_RULE = (
    "You cannot open links unless one of your tools can. If your input mentions a link "
    "whose content is not included, say so, and never describe or summarise a page you "
    "have not read."
)
#: Added to the planner's guide for generation and revision alike (§3). That guide
#: goes through ``str.format``, so this text holds no braces.
LINKS_PLANNER_GUIDE = """\
An agent cannot open a link unless one of its tools can. When the work depends on a web \
page or a document whose content the user has not given (a link alone is not its \
content), declare an input for that content, and write in its description which page \
or document it needs and that the user adds it in the run form \
with "Attach a document" or "Add a web page".

"""


def tool_guidance(tools: Collection[str]) -> list[str]:
    """What a step agent with these tools (their names) is told: how to use them when
    it has any, the web wording only with a tool that reads the web, and, whatever its
    tools, that it cannot open a link on its own."""
    guidance = [STEP_AGENT_TOOL_GUIDANCE] if tools else []
    if OUTBOUND_TOOLS.intersection(tools):
        guidance.append(STEP_AGENT_WEB_GUIDANCE)
    if SAVE_ARTIFACT in tools:
        guidance.append(STEP_AGENT_SAVE_GUIDANCE)
    return [*guidance, LINKS_RULE]

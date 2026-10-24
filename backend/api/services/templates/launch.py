"""The product launch template: positioning, market context and channels are
worked out in parallel, then turned into one dated, budgeted plan."""

from __future__ import annotations

from api.services.multiagent.contracts import InputField
from api.services.templates.contracts import (
    WEB_RESEARCH,
    MissionTemplate,
    TemplateStep,
)
from api.services.templates.review import Review
from api.services.toolbox.tools import CALCULATOR, CURRENT_DATETIME

LAUNCH_POSITIONING = """Write the positioning and messaging for this launch.
Product: {product}
Launch goal: {goal}

Include:
- the target customer, and the main problem they have
- a positioning statement: For [target customer] who [need], [product] is a [category] \
that [key benefit]. Unlike [main alternative], it [key difference].
- three key messages, each with a proof point
- a tagline of at most eight words
- the three objections buyers are most likely to raise, each with a short answer

Base everything on the product description, and label any claim it does not support as an \
assumption to confirm."""

LAUNCH_CONTEXT = """Research the market this product launches into: {product}
Launch date and resources: {launch}

Check today's date first. If you can search the web, find:
- the alternatives customers use today, and how they are priced
- recent launches, news or shifts in this space
- events, seasons or holidays around the launch date that could help or hurt it

Give the URL of every source. If you cannot search, give what you know and label it as \
unverified."""

LAUNCH_CHANNELS = """Choose the launch channels for this product: {product}
Launch goal: {goal}
Launch date and resources: {launch}

Recommend four to six channels, for example email, social media, communities, \
partnerships, press, paid ads or launch platforms. For each one, give: why it fits this \
product and its customers, the tactic, its share of the budget, the metric to watch, and \
what it should bring towards the goal. Split the budget with the calculator, so the shares \
add up exactly to the total, and state the assumptions behind every estimate."""

LAUNCH_DRAFT = """Write the launch plan for this product: {product}
Launch goal: {goal}
Launch date and resources: {launch}

Check today's date, then use the work below to write:
1. Summary: the plan in five bullets
2. Positioning and key messages
3. Channels and budget, as a table
4. Timeline: week by week, from now until four weeks after the launch, with dated tasks \
and an owner role for each, e.g. "marketing lead"
5. Launch day checklist
6. Metrics and targets that add up to the launch goal
7. Risks, each with how to prevent or handle it

Work so far:
{input}"""

PRODUCT_LAUNCH_PLAN = MissionTemplate(
    slug="product-launch-plan",
    title="Product launch plan",
    category="Marketing",
    description="Plan a launch: positioning, channels, budget, timeline and risks.",
    inputs=(
        InputField(
            "product",
            "Product",
            "What you are launching, who it is for, and what makes it different.",
        ),
        InputField(
            "goal",
            "Launch goal",
            "What success looks like, e.g. '1,000 sign-ups in the first month'.",
        ),
        InputField(
            "launch",
            "Launch date and resources",
            "When you launch and what you have to work with, e.g. 'March 15, a budget of "
            "20,000 EUR, two marketers'.",
        ),
    ),
    steps=(
        TemplateStep(
            title="Positioning and messaging",
            role="Product marketer",
            prompt=LAUNCH_POSITIONING,
            expected_output="Starts with the heading '## Positioning and messaging', then the "
            "target customer, a positioning statement, three messages with proof points, a "
            "tagline and three objections with answers.",
            stage=1,
        ),
        TemplateStep(
            title="Market context",
            role="Market researcher",
            prompt=LAUNCH_CONTEXT,
            expected_output="Starts with the heading '## Market context', then the "
            "alternatives with their pricing, recent relevant news, and dates around the "
            "launch that could help or hurt, with source URLs.",
            stage=1,
            tools=(*WEB_RESEARCH, CURRENT_DATETIME),
        ),
        TemplateStep(
            title="Channels and budget",
            role="Growth marketer",
            prompt=LAUNCH_CHANNELS,
            expected_output="Starts with the heading '## Channels and budget', then a table of "
            "four to six channels with tactic, budget, metric and expected result, totals "
            "that add up, and the assumptions.",
            stage=1,
            tools=(CALCULATOR,),
        ),
        TemplateStep(
            title="Launch plan draft",
            role="Launch manager",
            prompt=LAUNCH_DRAFT,
            expected_output="A launch plan in Markdown with the seven sections asked for, "
            "including a dated week-by-week timeline and measurable targets.",
            stage=2,
            tools=(CURRENT_DATETIME,),
        ),
        Review(
            title="Final launch plan",
            deliverable="launch plan",
            request="Product: {product}\nLaunch goal: {goal}\nLaunch date and resources: {launch}",
            checks=(
                "The timeline leads up to the stated launch date, and its dates are in order.",
                "Spending never exceeds the resources in the brief, and every total adds up; "
                "re-check the sums with the calculator.",
                "Targets are measurable and together reach the launch goal.",
                "Every channel has an owner, a metric and a budget.",
                "Each risk has a concrete way to prevent or handle it.",
                "The messages are consistent from one section to the next.",
            ),
            expected_output="The final launch plan in Markdown, with the same seven sections, "
            "corrected and ready to share.",
            tools=(CALCULATOR,),
        ).step(stage=3),
    ),
)

TEMPLATES = (PRODUCT_LAUNCH_PLAN,)

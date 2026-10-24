"""Research templates: briefs built from what the web says today.

Each researcher works in parallel and starts its result with its own heading,
so the writer after them can tell the parts apart. Without web tools the
researchers fall back on what the model knows and say so.
"""

from __future__ import annotations

from api.services.multiagent.contracts import InputField
from api.services.templates.contracts import (
    WEB_RESEARCH,
    MissionTemplate,
    TemplateStep,
)
from api.services.templates.review import Review
from api.services.toolbox.tools import CALCULATOR, CURRENT_DATETIME

# --- Market research brief ---------------------------------------------------

MARKET_SIZE = """Research the size and growth of this market: {market}
The research feeds a brief that must help decide: {goal}

Check today's date first, so you can say how recent each figure is. Then find:
- the market's current size, in value and, if it matters, in volume
- its growth over the last three to five years, and the forecast for the next three
- the main drivers and brakes of that growth

Prefer recent industry reports, official statistics and reputable press. Give every \
figure with the year it describes and the URL of its source. Use the calculator for any \
growth rate, share or currency conversion you work out yourself. When sources disagree, \
show the range instead of picking one. If you cannot find a reliable figure, say so and \
give a clearly labelled estimate with your reasoning."""

MARKET_CUSTOMERS = """Describe who buys in this market, and why: {market}
The research feeds a brief that must help decide: {goal}

Identify two to four customer segments. For each one, explain:
- who they are, and roughly how many there are if a source says
- the job they need done, and what they value most when choosing
- how and where they buy, and how sensitive they are to price
- what frustrates them about the options they have today

Base this on evidence such as surveys, reviews, forums and industry reports, and give the \
URL of each source. Label anything you infer without a source as an assumption."""

MARKET_TRENDS = """Find what will shape this market over the next two to three years: {market}
The research feeds a brief that must help decide: {goal}

Check today's date first. Then look for shifts in demand, technology, regulation, prices \
and competition, and for the risks they bring. For each trend or risk, give:
- what is happening, in one or two sentences
- the evidence, with its source's URL and date
- its likely impact on the goal above (high, medium or low), and why

Focus on what matters for the goal; leave out generic trends that would apply to any \
market."""

MARKET_BRIEF = """Write a market research brief on: {market}
It must help the reader decide: {goal}

Use only the research below; do not add facts it does not contain. Structure the brief as:
1. Summary: at most five bullets that answer the goal directly
2. Market size and growth
3. Customers and their needs
4. Trends
5. Risks
6. Recommendation: three to five concrete next steps tied to the goal, each with its reason
7. Sources: every URL the brief relies on

Keep each figure with its year and source. Where the research is thin or sources \
disagree, say so plainly instead of smoothing it over. Write for a busy decision-maker: \
short paragraphs, plain words, no filler.

Research:
{input}"""

MARKET = InputField(
    "market",
    "Market",
    "The market or product category to research, with the region if it matters, "
    "e.g. 'plant-based snacks in Germany'.",
)
GOAL = InputField(
    "goal",
    "Your goal",
    "What the brief should help you decide, e.g. 'whether to launch a premium range next year'.",
)

MARKET_RESEARCH_BRIEF = MissionTemplate(
    slug="market-research-brief",
    title="Market research brief",
    category="Research",
    description="Size up a market: its size, customers, trends and risks, in a brief you can "
    "act on.",
    inputs=(MARKET, GOAL),
    steps=(
        TemplateStep(
            title="Market size and growth",
            role="Market analyst",
            prompt=MARKET_SIZE,
            expected_output="Starts with the heading '## Market size and growth', then a table "
            "(metric, value, year, source URL) and three to five bullets on what drives and "
            "slows growth.",
            stage=1,
            tools=(*WEB_RESEARCH, CURRENT_DATETIME, CALCULATOR),
        ),
        TemplateStep(
            title="Customers and needs",
            role="Customer researcher",
            prompt=MARKET_CUSTOMERS,
            expected_output="Starts with the heading '## Customers and needs', then one short "
            "section per segment: who they are, their needs, how they buy and what frustrates "
            "them, with sources.",
            stage=1,
            tools=WEB_RESEARCH,
        ),
        TemplateStep(
            title="Trends and risks",
            role="Industry analyst",
            prompt=MARKET_TRENDS,
            expected_output="Starts with the heading '## Trends and risks', then four to six "
            "trends and three to five risks, each with evidence, a dated source URL and an "
            "impact rating.",
            stage=1,
            tools=(*WEB_RESEARCH, CURRENT_DATETIME),
        ),
        TemplateStep(
            title="Brief draft",
            role="Strategy writer",
            prompt=MARKET_BRIEF,
            expected_output="A market research brief in Markdown with the seven sections asked "
            "for, about 600 to 900 words, every figure traceable to a source.",
            stage=2,
        ),
        Review(
            title="Final brief",
            deliverable="market research brief",
            request="Market: {market}\nGoal: {goal}",
            checks=(
                "The summary answers the goal directly, in five bullets or fewer.",
                "All seven sections are there, in order: summary, market size and growth, "
                "customers, trends, risks, recommendation, sources.",
                "Every figure has a year and a source; label any figure without one as an "
                "estimate, or remove it.",
                "Figures and claims agree from one section to the next.",
                "The recommendation follows from the evidence and gives concrete next steps.",
                "The language is plain and concise, without filler or repetition.",
            ),
            expected_output="The final market research brief in Markdown, with the same seven "
            "sections, corrected and ready to share.",
        ).step(stage=3),
    ),
)

# --- Competitor analysis -----------------------------------------------------

COMPETITOR_PROFILES = """Profile each of these competitors: {competitors}
They compete with this product: {product}

Check today's date first. For each competitor, find:
- what they sell, and to whom
- their positioning and key messages, quoting their own website where you can
- their pricing and plans
- their standout features
- their strengths and weaknesses, from independent sources such as reviews or analysts
- notable moves in the last twelve months: launches, funding, price changes, partnerships

Read each competitor's own website and at least one independent source, and give the URL \
of every source. If something is not public, write "Not found" instead of guessing."""

CUSTOMER_VOICE = """Find out what customers say about these competitors: {competitors}

Look at review sites, app stores, forums and social media. For each competitor, summarise \
the most common praise and the most common complaints, with one or two short quotes and \
the URL of each. Then list the complaints and unmet needs that come up for several \
competitors at once. These are openings for this product: {product}"""

COMPARISON = """Compare this product with its competitors, and find where it can win.
Our product: {product}
Competitors: {competitors}

Using the research below, write:
1. A comparison table with one column per competitor and one for our product, and rows for \
target customer, positioning, pricing, key features, strengths and weaknesses. For our \
product, use only what its description says and write "unknown" for the rest.
2. Where our product is ahead, on par and behind, as three short lists.
3. Three to five openings: needs or customers the competitors serve poorly, each backed by \
evidence from the research.
4. Three to five recommended moves on product, pricing or messaging, each with its reason.
5. Sources: every URL the analysis relies on.

Research:
{input}"""

PRODUCT = InputField(
    "product",
    "Your product",
    "What you sell, to whom and at what price, in two or three sentences.",
)
COMPETITORS = InputField(
    "competitors",
    "Competitors",
    "The two to five competitors to compare, separated by commas.",
)

COMPETITOR_ANALYSIS = MissionTemplate(
    slug="competitor-analysis",
    title="Competitor analysis",
    category="Research",
    description="Compare your product with its rivals and find the gaps you can win.",
    inputs=(PRODUCT, COMPETITORS),
    steps=(
        TemplateStep(
            title="Competitor profiles",
            role="Competitive intelligence researcher",
            prompt=COMPETITOR_PROFILES,
            expected_output="Starts with the heading '## Competitor profiles', then one section "
            "per competitor with the same fields in the same order, each fact followed by its "
            "source URL.",
            stage=1,
            tools=(*WEB_RESEARCH, CURRENT_DATETIME),
        ),
        TemplateStep(
            title="What customers say",
            role="Review analyst",
            prompt=CUSTOMER_VOICE,
            expected_output="Starts with the heading '## What customers say', then praise and "
            "complaints per competitor with quotes and source URLs, and the needs several "
            "competitors leave unmet.",
            stage=1,
            tools=WEB_RESEARCH,
        ),
        TemplateStep(
            title="Comparison draft",
            role="Competitive strategist",
            prompt=COMPARISON,
            expected_output="A competitor analysis in Markdown: a comparison table, ahead / on "
            "par / behind lists, three to five openings, three to five recommended moves and "
            "the sources.",
            stage=2,
        ),
        Review(
            title="Final analysis",
            deliverable="competitor analysis",
            request="Our product: {product}\nCompetitors: {competitors}",
            checks=(
                "Every competitor named in the brief appears in the table and in the text.",
                "The table agrees with the text, and no cell is empty: write 'unknown' or "
                "'not found' instead.",
                "Facts about competitors have a source, and nothing said about our product "
                "goes beyond its description.",
                "Each opening and recommended move follows from the evidence.",
                "The language is plain and concise.",
            ),
            expected_output="The final competitor analysis in Markdown, with the same five "
            "parts, corrected and ready to share.",
        ).step(stage=3),
    ),
)

TEMPLATES = (MARKET_RESEARCH_BRIEF, COMPETITOR_ANALYSIS)

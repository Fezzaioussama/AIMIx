"""Marketing templates: content that has to rank, a calendar to publish to.

Web research is optional: without web tools the researchers describe what
usually works and say that it is not based on live results.
"""

from __future__ import annotations

from api.services.templates.contracts import (
    WEB_RESEARCH,
    MissionTemplate,
    TemplateInput,
    TemplateStep,
)
from api.services.templates.review import Review
from api.services.toolbox.tools import CURRENT_DATETIME

# --- SEO content brief -------------------------------------------------------

SEO_INTENT = """Work out the search intent and keywords for an article on: {topic}
Reader and goal: {audience}

If you can search the web, search the main keyword and two or three close variants, and \
look at what ranks and at the related questions people ask. Then report:
- the dominant search intent (informational, commercial, transactional or navigational) \
and what the searcher wants to achieve
- one primary keyword
- 8 to 15 secondary keywords and long-tail phrases, grouped by subtopic, each with a \
priority: high, medium or low
- 5 to 10 questions people ask about the topic

Never invent search volumes: give priorities instead, unless a source shows real numbers."""

SEO_RANKING = """Review the pages that rank today for: {topic}
Reader and goal: {audience}

If you can search and read web pages, open the top three to five results. For each, note \
its URL, its format (guide, list, comparison, tool...), roughly how long it is, its main \
sections, what it does well and what it misses. Then list three to six content gaps: \
questions none of them answers well, outdated facts, missing examples, data or visuals.

If you cannot browse the web, describe what strong content on this topic usually covers, \
and say clearly that it is not based on live results."""

SEO_BRIEF = """Write an SEO content brief for an article on: {topic}
Reader and goal: {audience}

Use the research below. Include:
1. A working title under 60 characters that contains the primary keyword, and two \
alternatives
2. A meta description under 155 characters
3. The search intent, in one sentence
4. The primary and secondary keywords, and where each belongs: title, headings or body
5. The recommended format and length
6. The outline: every H2 and H3 heading, each with one or two lines on what it covers
7. The questions to answer, as an FAQ section
8. The content gaps this article fills, and how
9. Ideas for internal and external links
10. The call to action, matched to the goal

Research:
{input}"""

TOPIC = TemplateInput(
    "topic",
    "Topic or main keyword",
    "What the article should rank for, e.g. 'how to choose running shoes'.",
)
READER_AND_GOAL = TemplateInput(
    "audience",
    "Reader and goal",
    "Who the article is for and what it should lead them to do, e.g. 'beginner runners; "
    "join our newsletter'.",
)

SEO_CONTENT_BRIEF = MissionTemplate(
    slug="seo-content-brief",
    title="SEO content brief",
    category="Marketing",
    description="Plan an article that can rank: search intent, keywords, outline and FAQ.",
    inputs=(TOPIC, READER_AND_GOAL),
    steps=(
        TemplateStep(
            title="Search intent and keywords",
            role="SEO specialist",
            prompt=SEO_INTENT,
            expected_output="Starts with the heading '## Search intent and keywords', then the "
            "intent, one primary keyword, grouped secondary keywords with priorities and 5 to "
            "10 questions people ask.",
            stage=1,
            tools=WEB_RESEARCH,
        ),
        TemplateStep(
            title="What ranks today",
            role="Content analyst",
            prompt=SEO_RANKING,
            expected_output="Starts with the heading '## What ranks today', then a short review "
            "of three to five ranking pages with their URLs, and three to six content gaps.",
            stage=1,
            tools=WEB_RESEARCH,
        ),
        TemplateStep(
            title="Brief draft",
            role="Content strategist",
            prompt=SEO_BRIEF,
            expected_output="An SEO brief in Markdown with the ten parts asked for, including an "
            "outline of H2 and H3 headings with notes for each section.",
            stage=2,
        ),
        Review(
            title="Final SEO brief",
            deliverable="SEO content brief",
            request="Topic or main keyword: {topic}\nReader and goal: {audience}",
            checks=(
                "The working title is under 60 characters and contains the primary keyword; "
                "count the characters.",
                "The meta description is under 155 characters and makes a clear promise.",
                "The outline matches the search intent and covers every listed question and "
                "content gap.",
                "Keywords sit naturally in the text, with no stuffing.",
                "The call to action fits the reader and the goal.",
            ),
            expected_output="The final SEO content brief in Markdown, with the same ten parts, "
            "corrected and ready to hand to a writer.",
        ).step(stage=3),
    ),
)

# --- Content calendar --------------------------------------------------------

CALENDAR_THEMES = """Find the content themes that will speak to this audience: {audience}
Topic: {topic}

Check today's date first, so the ideas fit the season and upcoming events. If you can \
search the web, look at what this audience reads and asks about right now: popular \
articles, forum questions, news. Propose four to six themes. For each one, give the angle, \
the need or question it answers for this audience, and two or three specific post ideas. \
Give the URL of anything you found online."""

CALENDAR_CHANNELS = """Write posting guidelines for these channels and this pace: {channels}
Topic: {topic}
Audience: {audience}

For each social network: the formats that work best, the ideal length, the tone, how to \
use hashtags or keywords, and the best days and times to post, with one example opening \
line. For the blog: the target length, the structure, and how each article will be reused \
on social media."""

CALENDAR_DRAFT = """Build a content calendar for: {topic}
Audience: {audience}
Channels and pace: {channels}

Check today's date, and start on the next Monday. Using the themes and guidelines below, \
make a table with one row per piece of content and these columns: date, channel, format, \
title or hook, theme, key message, call to action. Follow the requested pace exactly, \
spread the themes evenly, and schedule each blog post before the social posts that reuse it.

After the table, write out the first week's social posts in full, and an outline of the \
first blog post.

Themes and guidelines:
{input}"""

CONTENT_CALENDAR = MissionTemplate(
    slug="content-calendar",
    title="Content calendar",
    category="Marketing",
    description="Plan blog and social posts around one topic, with the first week written.",
    inputs=(
        TemplateInput(
            "topic",
            "Topic or product",
            "What the content is about, e.g. 'our new budgeting app'.",
        ),
        TemplateInput(
            "audience",
            "Audience",
            "Who you want to reach and what they care about.",
        ),
        TemplateInput(
            "channels",
            "Channels and pace",
            "Which networks, for how long and how often, e.g. 'LinkedIn and Instagram, 4 "
            "weeks, 1 blog post and 3 social posts a week'.",
        ),
    ),
    steps=(
        TemplateStep(
            title="Content themes",
            role="Content strategist",
            prompt=CALENDAR_THEMES,
            expected_output="Starts with the heading '## Content themes', then four to six "
            "themes, each with its angle, the audience need it serves and two or three post "
            "ideas.",
            stage=1,
            tools=(*WEB_RESEARCH, CURRENT_DATETIME),
        ),
        TemplateStep(
            title="Channel guidelines",
            role="Social media strategist",
            prompt=CALENDAR_CHANNELS,
            expected_output="Starts with the heading '## Channel guidelines', then one short "
            "section per channel (formats, length, tone, hashtags, timing) and how blog posts "
            "are reused on social media.",
            stage=1,
        ),
        TemplateStep(
            title="Calendar draft",
            role="Content planner",
            prompt=CALENDAR_DRAFT,
            expected_output="A Markdown table covering the whole period at the requested pace, "
            "then the first week's social posts in full and an outline of the first blog post.",
            stage=2,
            tools=(CURRENT_DATETIME,),
        ),
        Review(
            title="Final calendar",
            deliverable="content calendar",
            request="Topic: {topic}\nAudience: {audience}\nChannels and pace: {channels}",
            checks=(
                "The number of posts per channel and per week matches the requested pace, "
                "over the whole period.",
                "Dates are real, in order, start on the Monday after today, and each weekday "
                "is right; check today's date and count from it.",
                "Every row has a clear hook and call to action, and no two posts are "
                "near-duplicates.",
                "Each post fits its network's length limits, and the tone suits the audience.",
                "The first week's posts and the blog outline match the table.",
            ),
            expected_output="The final content calendar in Markdown: the corrected table, then "
            "the first week's social posts and the first blog post's outline.",
            tools=(CURRENT_DATETIME,),
        ).step(stage=3),
    ),
)

TEMPLATES = (SEO_CONTENT_BRIEF, CONTENT_CALENDAR)

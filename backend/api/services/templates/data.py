"""The data template: answers a question from a CSV file or a pasted table.

The data arrives in the run input (a pasted table, or an attached CSV), or as
the name of a CSV file in the user's workspace that the agents open with their
file tools. Every figure goes through the calculator rather than the model's
mental arithmetic.
"""

from __future__ import annotations

from api.services.multiagent.contracts import InputField
from api.services.templates.contracts import MissionTemplate, TemplateStep
from api.services.templates.review import Review
from api.services.toolbox.tools import CALCULATOR, LIST_WORKSPACE_FILES, READ_CSV

#: Open a workspace CSV by name, and compute exactly.
DATA_TOOLS = (LIST_WORKSPACE_FILES, READ_CSV, CALCULATOR)

DATA_PROFILE = """Profile this dataset, so the analysis built on it can be trusted. The \
question it should answer is: {question}

If the data below is the name of a workspace file rather than the data itself, find it \
and open it with your file tools; if you cannot, say so.

Report:
- how many rows and columns there are, and what one row represents
- each column: its name, type, unit and an example value
- data quality problems: missing or invalid values, duplicates, mixed units or formats, \
and extreme values that look like errors
- what the data cannot tell, given the question, e.g. a period too short to show a trend

Count from the rows themselves and use the calculator for any arithmetic; never estimate. \
If you can see only part of the data, say how many rows you profiled. Do not answer the \
question yet.

Data:
{data}"""

DATA_ANALYSIS = """Answer this question from the data below: {question}

If the data is the name of a workspace file rather than the data itself, find it and \
open it with your file tools; if you cannot, say so.

Work step by step:
- pick the columns and rows that bear on the question
- compute the figures that answer it: totals, averages, shares, changes over time, \
comparisons between groups. Use the calculator for every figure; never estimate by eye
- look for trends, outliers and surprising differences, and check whether missing data or \
a few extreme rows could explain them

Report each finding with its exact figure and how you computed it. If you can see only \
part of the data, say how many rows you analysed.

Data:
{data}"""

DATA_REPORT = """Write a short insights report that answers: {question}

Use only the profile and analysis below. Structure:
1. Answer: two or three sentences that answer the question directly, with the key figure
2. Key findings: three to six, most important first, each with its figure
3. Trends and outliers worth a closer look
4. Caveats: the data quality problems and limits that affect the answer
5. Recommended actions: two to four, each tied to a finding
6. Next analyses: the extra data or analysis that would make the answer stronger

Use a table wherever it makes figures easier to compare, and keep every figure exactly as \
the analysis gives it.

Profile and analysis:
{input}"""

DATA_INSIGHTS_REPORT = MissionTemplate(
    slug="data-insights-report",
    title="Data insights report",
    category="Data",
    description="Find the trends, outliers and answers in a CSV file or a table.",
    inputs=(
        InputField(
            "data",
            "Data",
            "Attach a CSV file or paste a table. You can also give the name of a CSV file in "
            "your workspace.",
        ),
        InputField(
            "question",
            "Your question",
            "What you want the data to tell you, e.g. 'Which products drive our revenue growth?'",
        ),
    ),
    steps=(
        TemplateStep(
            title="Data profile",
            role="Data analyst",
            prompt=DATA_PROFILE,
            expected_output="Starts with the heading '## Data profile', then the row and "
            "column counts, a table of columns (name, type, unit, example) and the data "
            "quality problems and limits.",
            stage=1,
            tools=DATA_TOOLS,
        ),
        TemplateStep(
            title="Analysis",
            role="Data analyst",
            prompt=DATA_ANALYSIS,
            expected_output="Starts with the heading '## Analysis', then a direct answer to the "
            "question and three to seven findings, each with its exact figure and how it was "
            "computed.",
            stage=1,
            tools=DATA_TOOLS,
        ),
        TemplateStep(
            title="Report draft",
            role="Insights writer",
            prompt=DATA_REPORT,
            expected_output="An insights report in Markdown with the six sections asked for, "
            "under one page, every figure taken from the analysis.",
            stage=2,
        ),
        Review(
            title="Final report",
            deliverable="insights report",
            request="Question: {question}",
            checks=(
                "The answer section answers the question directly, with a figure.",
                "Figures agree from one section to the next; re-check sums, shares and "
                "changes with the calculator.",
                "Every finding rests on a figure, and nothing claims more than the data shows.",
                "The caveats name every data problem that affects the answer.",
                "Each recommended action follows from a finding.",
            ),
            expected_output="The final insights report in Markdown, with the same six "
            "sections, corrected and ready to share.",
            tools=(CALCULATOR,),
        ).step(stage=3),
    ),
)

TEMPLATES = (DATA_INSIGHTS_REPORT,)

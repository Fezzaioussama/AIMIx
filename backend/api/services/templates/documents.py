"""Templates that work on a document the user brings: pasted, or attached to the
run input (PDF, Word, HTML, CSV or text), so they need no tools.

Readers work in parallel on the same text; the final reviewer re-reads the
original, so the deliverable stays faithful to it.
"""

from __future__ import annotations

from api.services.templates.contracts import MissionTemplate, TemplateInput, TemplateStep
from api.services.templates.review import Review

# --- Document digest ---------------------------------------------------------

DIGEST_KEY_POINTS = """Read the document below and pull out what matters most to this \
reader: {reader}

List the five to ten most important points: decisions, facts, figures, commitments, dates \
and deadlines, most important first. Keep names, figures and dates exactly as the document \
writes them, and say where each point comes from (section, page or heading) when the \
document shows it.

Document:
{document}"""

DIGEST_RISKS = """Read the document below as a careful reviewer for this reader: {reader}

Find the risks and obligations it creates: costs, deadlines, liabilities, penalties, \
commitments, one-sided terms, and wording vague enough to be read two ways. For each one, \
quote the exact words briefly, explain the risk in plain language, and rate it high, medium \
or low. Order them from highest to lowest. If the document has none of a kind, do not \
invent one.

Document:
{document}"""

DIGEST_QUESTIONS = """Read the document below and find what it leaves unclear for this \
reader: {reader}

Look for missing information, undefined terms, assumptions it does not justify, sections \
that contradict each other, and points that need a decision or a follow-up. Write each one \
as a question to put to the document's author or owner, followed by one line on why it \
matters.

Document:
{document}"""

DIGEST_DRAFT = """Combine the three analyses below into one digest of the document for this \
reader: {reader}

Structure:
1. Summary: three sentences on what the document is and what it means for the reader
2. Key points
3. Risks and obligations, as a table with the columns: risk, quote, rating
4. Open questions
5. Next steps: three to five actions the reader should take

Merge duplicates, keep the most specific wording, and add nothing the analyses do not \
support. Keep it to about one page.

Analyses:
{input}"""

DOCUMENT_DIGEST = MissionTemplate(
    slug="document-digest",
    title="Document digest",
    category="Documents",
    description="Turn a long document into its key points, risks and open questions.",
    inputs=(
        TemplateInput(
            "document",
            "Document",
            "Paste the text, or attach a PDF, Word or text file.",
        ),
        TemplateInput(
            "reader",
            "Who it is for",
            "Who will read the digest and what they need from it, e.g. 'our legal team, "
            "deciding whether to sign'.",
        ),
    ),
    steps=(
        TemplateStep(
            title="Key points",
            role="Analyst",
            prompt=DIGEST_KEY_POINTS,
            expected_output="Starts with the heading '## Key points', then five to ten "
            "bullets, most important first, each saying where it appears in the document.",
            stage=1,
        ),
        TemplateStep(
            title="Risks and obligations",
            role="Risk reviewer",
            prompt=DIGEST_RISKS,
            expected_output="Starts with the heading '## Risks and obligations', then each "
            "risk with a short quote, a plain explanation and a high, medium or low rating, "
            "highest first.",
            stage=1,
        ),
        TemplateStep(
            title="Open questions",
            role="Critical reader",
            prompt=DIGEST_QUESTIONS,
            expected_output="Starts with the heading '## Open questions', then three to ten "
            "questions, each followed by one line on why it matters.",
            stage=1,
        ),
        TemplateStep(
            title="Digest draft",
            role="Editor",
            prompt=DIGEST_DRAFT,
            expected_output="A one-page digest in Markdown: a three-sentence summary, key "
            "points, a risk table, open questions and three to five next steps.",
            stage=2,
        ),
        Review(
            title="Final digest",
            deliverable="document digest",
            request="Who it is for: {reader}",
            source="Original document:\n{document}",
            checks=(
                "Every point, quote, figure, name and date matches the original exactly.",
                "Nothing in the digest is absent from the original or contradicts it.",
                "No important risk, obligation or deadline in the original is left out.",
                "The summary speaks to the reader's needs, and the next steps are concrete.",
                "The five sections are there, and the digest fits on about one page.",
            ),
            expected_output="The final digest in Markdown, faithful to the document, with the "
            "same five sections.",
        ).step(stage=3),
    ),
)

# --- Meeting notes to actions -------------------------------------------------

MEETING_DECISIONS = """Read the meeting notes below and list every decision that was made.
About the meeting: {meeting}

A decision is something the group agreed, approved, rejected or chose; an idea that was \
only discussed is not one. For each decision, give:
- the decision, in one sentence
- who made it or owns it, if the notes say
- the reason, if the notes give one

Then list, under "Still open", the topics discussed without a decision.

Notes:
{notes}"""

MEETING_ACTION_ITEMS = """List every action item in the meeting notes below.
About the meeting: {meeting}

Include explicit tasks and implied commitments such as "I'll send the deck", but never \
invent a task. For each one, give:
- the task, starting with a verb
- the owner, using a name from the notes, or "Unassigned"
- the due date exactly as the notes state it, or "Not set"
- any dependency on another task or person

Notes:
{notes}"""

MEETING_FOLLOW_UP = """Write the follow-up to this meeting from the decisions and action \
items below.
About the meeting: {meeting}

Produce:
1. Summary: three to five sentences on what the meeting covered and concluded
2. Decisions
3. Action items, as a table with the columns: task, owner, due date
4. Still open: the questions that remain
5. Follow-up email: a subject line, then a short, friendly message to the attendees with \
the summary, the decisions and each person's actions, ready to send

Keep the tone neutral, and write names exactly as they appear below.

Decisions and action items:
{input}"""

MEETING_NOTES_TO_ACTIONS = MissionTemplate(
    slug="meeting-actions",
    title="Meeting notes to actions",
    category="Documents",
    description="Turn meeting notes or a transcript into decisions, action items and a "
    "follow-up email.",
    inputs=(
        TemplateInput(
            "notes",
            "Meeting notes or transcript",
            "Paste the notes or the transcript, or attach a file.",
        ),
        TemplateInput(
            "meeting",
            "About the meeting",
            "What it was about and who attended, with their roles, e.g. 'Weekly product "
            "sync: Ana (product), Ben (design), Chloe (engineering)'.",
        ),
    ),
    steps=(
        TemplateStep(
            title="Decisions",
            role="Meeting analyst",
            prompt=MEETING_DECISIONS,
            expected_output="Starts with the heading '## Decisions', then numbered decisions "
            "with their owner and reason when known, then a 'Still open' list.",
            stage=1,
        ),
        TemplateStep(
            title="Action items",
            role="Project coordinator",
            prompt=MEETING_ACTION_ITEMS,
            expected_output="Starts with the heading '## Action items', then a table with the "
            "columns task, owner, due date and dependency, one row per action.",
            stage=1,
        ),
        TemplateStep(
            title="Follow-up draft",
            role="Communications writer",
            prompt=MEETING_FOLLOW_UP,
            expected_output="Markdown with a summary, decisions, an action table, open "
            "questions and a ready-to-send follow-up email with a subject line.",
            stage=2,
        ),
        Review(
            title="Final follow-up",
            deliverable="meeting follow-up",
            request="About the meeting: {meeting}",
            source="Original notes:\n{notes}",
            checks=(
                "Every decision was really made in the notes, and none is missing.",
                "Every action item, owner and due date matches the notes, none is missing, "
                "and no task is invented.",
                "Names are spelled exactly as in the notes.",
                "The email agrees with the lists and is ready to send.",
            ),
            expected_output="The final follow-up in Markdown, faithful to the notes, with the "
            "same five parts, including the ready-to-send email.",
        ).step(stage=3),
    ),
)

TEMPLATES = (DOCUMENT_DIGEST, MEETING_NOTES_TO_ACTIONS)

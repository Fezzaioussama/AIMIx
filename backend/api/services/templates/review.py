"""The step every template ends with: a reviewer that checks the draft against
the request and returns the corrected, final version (AGENTS.md §7 Builder).

One builder keeps the eight reviewers consistent; each template supplies only
what is particular to it: the request, the checklist and the expected output.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.models import RESERVED_INPUT_NAME
from api.services.templates.contracts import TemplateStep

REVIEWER_ROLE = "Editor and fact-checker"

#: ``{input}``: the previous stage's output, i.e. the draft. A constant, since
#: inside the f-strings below the braces would be read as an expression.
DRAFT = "{" + RESERVED_INPUT_NAME + "}"


@dataclass(frozen=True)
class Review:
    title: str
    #: What is reviewed, as the reviewer should call it, e.g. "market research brief".
    deliverable: str
    #: What the user asked for, restated from the template's inputs, e.g.
    #: "Market: {market}".
    request: str
    checks: tuple[str, ...]
    expected_output: str
    #: Material the draft must stay faithful to, with its label, e.g.
    #: "Original document:\n{document}"; empty when the request is enough.
    source: str = ""
    tools: tuple[str, ...] = ()

    def step(self, stage: int) -> TemplateStep:
        """The reviewer as the template's last, and only output, step."""
        return TemplateStep(
            title=self.title,
            role=REVIEWER_ROLE,
            prompt=self._prompt(),
            expected_output=self.expected_output,
            stage=stage,
            tools=self.tools,
            is_output=True,
        )

    def _prompt(self) -> str:
        against = "the request and the original" if self.source else "the request"
        checklist = "\n".join(f"- {check}" for check in self.checks)
        source = f"{self.source}\n\n" if self.source else ""
        return (
            f"You are the final reviewer. This {self.deliverable} goes to the person who "
            "asked for it as soon as you are done.\n\n"
            f"Their request:\n{self.request}\n\n"
            f"Check the draft below against {against}, and fix every problem you find:\n"
            f"{checklist}\n\n"
            f"Return only the corrected, final {self.deliverable}, complete and ready to use. "
            "Do not list your changes or comment on the draft.\n\n"
            f"{source}Draft:\n{DRAFT}"
        )

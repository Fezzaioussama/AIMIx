"""Reduce an HTML page to the readable text an agent needs (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

WHITESPACE = re.compile(r"\s+")

#: Elements whose content is never prose.
SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "iframe"})
#: Elements that start a new line in rendered text.
BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "figcaption", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
        "li", "main", "nav", "ol", "p", "pre", "section", "table", "title", "tr", "ul",
    }
)  # fmt: skip


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        # Source newlines are plain whitespace in HTML; only block tags break lines.
        if not self._skip_depth:
            self._parts.append(WHITESPACE.sub(" ", data))

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._parts).split("\n"))
        return "\n".join(line for line in lines if line)


def html_to_text(markup: str) -> str:
    """Visible text, one block per line, with whitespace collapsed."""
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return parser.text()

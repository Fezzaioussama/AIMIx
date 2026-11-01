"""Reduce an HTML page to the readable text an agent needs (stdlib only).

Shared by fetch_url, uploaded .html files and the pages users read from a link
(AGENTS.md §3): the same charset rules (``text_charset``, ``page_charset``) and the
same text for all three.
"""

from __future__ import annotations

import codecs
import re
from html.parser import HTMLParser

WHITESPACE = re.compile(r"\s+")

#: How far into a page its own charset declaration is looked for. The HTML
#: standard's prescan stops at 1024 bytes; real pages put the tag later, behind
#: long heads.
PRESCAN_BYTES = 4096
#: ``<meta charset="x">`` and ``<meta http-equiv="Content-Type" content="...; charset=x">``.
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I)
#: Codecs a page may name as its charset that are not character sets: they
#: raise on ordinary text ("idna", "undefined") or take quadratic time ("punycode").
#: Bytes-to-bytes codecs ("zlib", "base64", "rot13") fail the decode and fall back too.
NOT_CHARSETS = frozenset({"idna", "punycode", "undefined"})
#: UTF-8, read so that a byte order mark never reaches the text.
FALLBACK_CHARSET = "utf-8-sig"
#: A byte order mark names the charset before anything else does.
BOM_CHARSETS = (
    (codecs.BOM_UTF8, FALLBACK_CHARSET),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

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
#: Table cells end with CELL_SEPARATOR, so "69,081,996" and "0.8%" never run together.
CELL_TAGS = frozenset({"td", "th"})
CELL_SEPARATOR = " | "


def _charset(name: str | None) -> str:
    try:
        codec = codecs.lookup(name or FALLBACK_CHARSET).name
    except LookupError:
        return FALLBACK_CHARSET
    return FALLBACK_CHARSET if codec in NOT_CHARSETS or codec == "utf-8" else codec


def decode_page(body: bytes, charset: str | None) -> str:
    """The page as text in its declared charset, or UTF-8 when that is no text
    codec at all; undecodable bytes become U+FFFD, never an error."""
    try:
        return body.decode(_charset(charset), errors="replace")
    except (LookupError, UnicodeError):  # "zlib" and friends are not text codecs
        return body.decode(FALLBACK_CHARSET, errors="replace")


def declared_charset(markup: bytes) -> str | None:
    """The charset a page names in a ``<meta>`` tag within its first PRESCAN_BYTES."""
    found = _META_CHARSET.search(markup[:PRESCAN_BYTES])
    return found.group(1).decode("ascii") if found else None


def text_charset(body: bytes, header: str | None = None) -> str | None:
    """The charset text is read in: the one its byte order mark names, else the one
    the Content-Type header names (``header``); None when neither names one."""
    for bom, charset in BOM_CHARSETS:
        if body.startswith(bom):
            return charset
    return header


def page_charset(body: bytes, header: str | None = None) -> str | None:
    """The charset an HTML page is read in, in the HTML standard's order: its byte
    order mark, the Content-Type header, then its own ``<meta>`` declaration."""
    return text_charset(body, header) or declared_charset(body)


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
        elif tag in CELL_TAGS:
            self._parts.append(CELL_SEPARATOR)

    def handle_data(self, data: str) -> None:
        # Source newlines are plain whitespace in HTML; only block tags break lines.
        if not self._skip_depth:
            self._parts.append(WHITESPACE.sub(" ", data))

    def text(self) -> str:
        # A row's last cell leaves a separator at the end of its line: drop it, and
        # a line of nothing else (a cell that ended after a block).
        lines = (" ".join(line.split()).rstrip(" |") for line in "".join(self._parts).split("\n"))
        return "\n".join(line for line in lines if line)


def html_to_text(markup: str) -> str:
    """Visible text, one block per line, with whitespace collapsed and table
    cells separated by `` | ``."""
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return parser.text()

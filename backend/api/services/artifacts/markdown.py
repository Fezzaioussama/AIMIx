"""Markdown into the small document model both writers lay out (§3: one parser).

Agents write Markdown; the Word and PDF writers walk these blocks instead of each
reading the text their own way. Raw HTML stays literal text, never markup. Each
Markdown node type maps to a builder (§7 Registry): an unknown block is skipped,
an unknown inline node keeps its text.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


@dataclass(frozen=True)
class Span:
    """A run of inline text and its style."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    #: Link target; empty when the span is not a link.
    href: str = ""


Spans = tuple[Span, ...]


@dataclass(frozen=True)
class Heading:
    level: int
    spans: Spans


@dataclass(frozen=True)
class Paragraph:
    spans: Spans


@dataclass(frozen=True)
class ListBlock:
    ordered: bool
    #: Number of the first item of an ordered list.
    start: int
    #: Each item holds blocks of its own: paragraphs, nested lists, ...
    items: tuple[tuple[Block, ...], ...]


@dataclass(frozen=True)
class Table:
    #: Empty when the table has no header row.
    header: tuple[Spans, ...]
    rows: tuple[tuple[Spans, ...], ...]


@dataclass(frozen=True)
class CodeBlock:
    text: str


@dataclass(frozen=True)
class Quote:
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Rule:
    """A thematic break, ``---``."""


Block = Heading | Paragraph | ListBlock | Table | CodeBlock | Quote | Rule
InlineHandler = Callable[[SyntaxTreeNode, Span, list[Span]], None]

#: Link targets a document keeps as links; any other link stays plain text.
LINK_SCHEMES = frozenset({"http", "https", "mailto"})
#: Characters no document can hold (XML forbids them): control characters other
#: than tab and line breaks, and halves of a surrogate pair.
_UNPRINTABLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def parse_markdown(text: str) -> tuple[Block, ...]:
    """CommonMark plus tables and strikethrough, with HTML kept as text."""
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    return _blocks(SyntaxTreeNode(parser.parse(_UNPRINTABLE.sub("", text))).children)


def plain_text(spans: Spans) -> str:
    return "".join(span.text for span in spans)


def web_link(span: Span) -> str:
    """The span's target when it is a web or mail link, else ''."""
    return span.href if urlsplit(span.href).scheme.lower() in LINK_SCHEMES else ""


def _blocks(nodes: list[SyntaxTreeNode]) -> tuple[Block, ...]:
    return tuple(_BLOCKS[node.type](node) for node in nodes if node.type in _BLOCKS)


def _list(node: SyntaxTreeNode, *, ordered: bool) -> Block:
    start = int(node.attrs.get("start", 1)) if ordered else 1
    return ListBlock(ordered, start, tuple(_blocks(item.children) for item in node.children))


def _table(node: SyntaxTreeNode) -> Block:
    rows = [
        tuple(_spans(cell) for cell in row.children)
        for section in node.children
        for row in section.children
    ]
    if rows and node.children[0].type == "thead":
        return Table(rows[0], tuple(rows[1:]))
    return Table((), tuple(rows))


_BLOCKS: dict[str, Callable[[SyntaxTreeNode], Block]] = {
    "heading": lambda node: Heading(int(node.tag[1:]), _spans(node)),
    "paragraph": lambda node: Paragraph(_spans(node)),
    "bullet_list": lambda node: _list(node, ordered=False),
    "ordered_list": lambda node: _list(node, ordered=True),
    "table": _table,
    "fence": lambda node: CodeBlock(node.content.rstrip("\n")),
    "code_block": lambda node: CodeBlock(node.content.rstrip("\n")),
    "blockquote": lambda node: Quote(_blocks(node.children)),
    "hr": lambda node: Rule(),
}


def _spans(node: SyntaxTreeNode) -> Spans:
    """The inline text of a heading, a paragraph or a table cell."""
    found: list[Span] = []
    _children(node, Span(""), found)
    return tuple(found)


def _children(node: SyntaxTreeNode, style: Span, found: list[Span]) -> None:
    for child in node.children:
        handler = _INLINE.get(child.type)
        if handler is not None:
            handler(child, style, found)
        elif child.content:
            found.append(replace(style, text=child.content))


def _styled(*, bold: bool = False, italic: bool = False) -> InlineHandler:
    """A handler for a node whose children share one more style, e.g. bold."""

    def handle(node: SyntaxTreeNode, style: Span, found: list[Span]) -> None:
        inner = replace(style, bold=style.bold or bold, italic=style.italic or italic)
        _children(node, inner, found)

    return handle


def _text(text: Callable[[SyntaxTreeNode], str], *, code: bool = False) -> InlineHandler:
    """A handler for a leaf node: its text in the style around it."""

    def handle(node: SyntaxTreeNode, style: Span, found: list[Span]) -> None:
        found.append(replace(style, text=text(node), code=style.code or code))

    return handle


def _link(node: SyntaxTreeNode, style: Span, found: list[Span]) -> None:
    _children(node, replace(style, href=str(node.attrs.get("href", ""))), found)


_INLINE: dict[str, InlineHandler] = {
    "inline": _styled(),
    "text": _text(lambda node: node.content),
    "code_inline": _text(lambda node: node.content, code=True),
    "softbreak": _text(lambda node: " "),
    "hardbreak": _text(lambda node: "\n"),
    "strong": _styled(bold=True),
    "em": _styled(italic=True),
    "s": _styled(),
    "link": _link,
    # An image cannot be shown in the document; its alt text is.
    "image": _styled(),
}

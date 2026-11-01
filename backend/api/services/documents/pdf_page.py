"""What pypdf's ``extract_text`` leaves out of a PDF page: how much of it pictures
cover and how large its text is printed, which tell a scan carrying a page number
from a page of text or a slide's title over a photo, and the filled form fields and
comments it shows, which live in its annotations.

Everything here reads pypdf's objects defensively: an entry that is missing,
broken or of the wrong type is ignored, as PDF viewers do, so damage there never
costs the page its text.
"""

from __future__ import annotations

import codecs
import math
from collections.abc import Iterator
from typing import Any

from pypdf import PageObject
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    PdfObject,
    TextStringObject,
)

#: How pypdf names an inline picture (BI ... ID ... EI) among a page's operations.
_INLINE_PICTURE = b"INLINE IMAGE"
#: Annotations whose /Contents is not a comment: a form field's widget (its value is
#: read as the field's), a popup (it repeats the comment it belongs to) and a link.
_NOT_COMMENTS = frozenset({"/Widget", "/Popup", "/Link"})
#: The value of a checkbox or radio button that is not ticked.
_UNTICKED = "/Off"
#: How far up its parents a widget's field is looked for, so a cycle ends.
_MAX_FIELD_DEPTH = 16


def picture_share(page: PageObject) -> float:
    """How much of ``page`` its pictures cover, from 0 to 1 (overlapping pictures
    count twice), from where its content stream draws them. Only the area matters,
    so of each transformation only its determinant is followed. A picture drawn
    inside a form XObject is not counted."""
    content = page.get_contents()
    pictures = _picture_names(page)
    # Most short pages (a title, a page of a slide deck) have no picture at all:
    # they are not parsed again. b"BI" may match other bytes too; that only costs a parse.
    if content is None or not (pictures or b"BI" in content.get_data()):
        return 0.0
    area = _page_area(page)
    return min(_covered(content.operations, pictures) / area, 1.0) if area else 0.0


def largest_print(page: PageObject) -> float:
    """The size, in points as printed, of the page's largest text (0 for none): a
    page number or a scanner app's footer is small print, a slide's title is not.
    Each piece is measured by its font size times how much both matrices scale it."""
    largest = 0.0

    def measure(text: str, cm: list[float], tm: list[float], _font: object, size: float) -> None:
        nonlocal largest
        if text.strip():
            scale = math.sqrt(abs(_determinant(cm) * _determinant(tm)))
            largest = max(largest, abs(size) * scale)

    page.extract_text(visitor_text=measure)
    return largest


def _covered(operations: list[tuple[Any, bytes]], pictures: frozenset[str]) -> float:
    """The area, in the page's units, that ``operations`` draw pictures over."""
    scale, covered = 1.0, 0.0
    saved: list[float] = []
    for operands, operator in operations:
        if operator == b"q":
            saved.append(scale)
        elif operator == b"Q" and saved:
            scale = saved.pop()
        elif operator == b"cm":
            scale *= _determinant(operands)
        elif _draws_picture(operator, operands, pictures):
            covered += abs(scale)  # a picture fills the unit square of the current space
    return covered


def _page_area(page: PageObject) -> float:
    """The area of the page's crop box, else of its media box; 0 when neither is
    four numbers (pypdf's own ``cropbox`` raises on such a page)."""
    for key in ("/CropBox", "/MediaBox"):
        box = _resolved(page.get(key))
        corners = [_resolved(value) for value in box] if isinstance(box, ArrayObject) else []
        numbers = [
            float(value) for value in corners if isinstance(value, (NumberObject, FloatObject))
        ]
        if len(numbers) == len(corners) == 4:
            left, bottom, right, top = numbers
            return abs((right - left) * (top - bottom))
    return 0.0


def _picture_names(page: PageObject) -> frozenset[str]:
    """The names the page's resources give its picture XObjects."""
    resources = _resolved(page.get("/Resources"))
    if not isinstance(resources, DictionaryObject):
        return frozenset()
    xobjects = _resolved(resources.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return frozenset()
    return frozenset(name for name, value in xobjects.items() if _is_picture(_resolved(value)))


def _is_picture(xobject: PdfObject | None) -> bool:
    return isinstance(xobject, DictionaryObject) and _name(xobject, "/Subtype") == "/Image"


def _draws_picture(operator: bytes, operands: list[Any], pictures: frozenset[str]) -> bool:
    if operator == _INLINE_PICTURE:
        return True
    return operator == b"Do" and bool(operands) and operands[0] in pictures


def _determinant(operands: list[Any]) -> float:
    """How much the ``cm`` matrix [a b c d e f] scales areas: a*d - b*c (1 if malformed)."""
    if len(operands) != 6 or not all(isinstance(value, (int, float)) for value in operands[:4]):
        return 1.0
    a, b, c, d = (float(value) for value in operands[:4])
    return a * d - b * c


class PageMarks:
    """Labelled lines for the filled form fields and the comments of each page of
    one PDF: ``[Form field Name: Jean Dupont]``, ``[Comment: Approved on 3 Oct]``.

    A field shown by several widgets (radio buttons, or one field on two pages) is
    said once, on the first page that shows it; empty fields and unticked boxes are
    not said at all.
    """

    def __init__(self) -> None:
        self._fields_seen: set[int] = set()

    def lines(self, page: PageObject) -> list[str]:
        lines: list[str] = []
        for annotation in _annotations(page):
            if _name(annotation, "/Subtype") == "/Widget":
                line = self._field_line(annotation)
            else:
                line = _comment_line(annotation)
            if line and line not in lines:
                lines.append(line)
        return lines

    def _field_line(self, widget: DictionaryObject) -> str | None:
        field = _field_of(widget)
        if field is None or id(field) in self._fields_seen:
            return None
        self._fields_seen.add(id(field))
        value = _value(_resolved(field.get("/V")))
        if not value:
            return None
        name = _text(_resolved(field.get("/TU"))) or _text(_resolved(field.get("/T")))
        return f"[Form field {name}: {value}]"


def _annotations(page: PageObject) -> Iterator[DictionaryObject]:
    annotations = _resolved(page.get("/Annots"))
    if not isinstance(annotations, ArrayObject):
        return
    for item in annotations:
        annotation = _resolved(item)
        if isinstance(annotation, DictionaryObject):
            yield annotation


def _field_of(widget: DictionaryObject) -> DictionaryObject | None:
    """The form field ``widget`` shows: itself when it is named (/T), else its
    nearest named parent (a radio button's group, say)."""
    node: PdfObject | None = widget
    for _ in range(_MAX_FIELD_DEPTH):
        if not isinstance(node, DictionaryObject):
            return None
        if "/T" in node:
            return node
        node = _resolved(node.get("/Parent"))
    return None


def _value(value: PdfObject | None) -> str:
    """A field's value as text: a ticked box by its export name (e.g. Yes), the
    items of a list joined, a number as written; "" for none."""
    if isinstance(value, NameObject):
        return "" if value == _UNTICKED else value[1:]
    if isinstance(value, ArrayObject):
        return ", ".join(filter(None, (_text(_resolved(item)) for item in value)))
    if isinstance(value, (NumberObject, FloatObject)):
        return str(value)
    return _text(value)


def _comment_line(annotation: DictionaryObject) -> str | None:
    if _name(annotation, "/Subtype") in _NOT_COMMENTS:
        return None
    text = _text(_resolved(annotation.get("/Contents")))
    return f"[Comment: {text}]" if text else None


def _name(dictionary: DictionaryObject, key: str) -> str:
    """The name at ``key``, e.g. "/Image"; "" when it is missing or not a name."""
    value = _resolved(dictionary.get(key))
    return str(value) if isinstance(value, NameObject) else ""


def _text(value: PdfObject | None) -> str:
    """A string on one line; "" for anything else (a stream, a number)."""
    return " ".join(_string(value).split())


def _string(value: PdfObject | None) -> str:
    """A PDF string as text. pypdf reads one as PDFDocEncoding unless it starts with a
    UTF-16 byte order mark, so a PDF 2.0 UTF-8 one (behind a UTF-8 BOM) is decoded
    here; one with a byte PDFDocEncoding lacks stays bytes (a C program's NUL at the
    end, UTF-8, Windows-1252): UTF-8 when it is, else Windows-1252, without NULs."""
    if isinstance(value, TextStringObject):
        raw = value.original_bytes
        if raw.startswith(codecs.BOM_UTF8):
            return raw[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace")
        return str(value)
    if not isinstance(value, ByteStringObject):
        return ""
    raw = bytes(value).replace(b"\x00", b"")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _resolved(value: PdfObject | None) -> PdfObject | None:
    """``value``, or the object it refers to: ``dict.get`` on a pypdf dictionary does
    not follow references the way indexing does."""
    return None if value is None else value.get_object()

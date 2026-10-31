"""What a file is called and what it is: safe upload names and media types."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from api.exceptions import ValidationFailed
from api.services.files.storage import NAME_MAX_BYTES, UNSAFE_NAME_CHARACTERS

_SPACES = re.compile(r"\s+")

#: Media type per extension, so a download is labelled the same on every server
#: (the system's mime.types differs between images). Anything else is binary. The
#: pictures let the app preview one (Missions' recent files); SVG stays binary, as
#: it can carry script.
MEDIA_TYPES = {
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".gif": "image/gif",
    ".htm": "text/html",
    ".html": "text/html",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".markdown": "text/markdown",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".txt": "text/plain",
    ".webp": "image/webp",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}
BINARY = "application/octet-stream"


def media_type(name: str) -> str:
    return MEDIA_TYPES.get(PurePosixPath(name).suffix.lower(), BINARY)


def file_type(name: str) -> str:
    """The lower-case extension without its dot, e.g. ``pdf``; empty without one."""
    return PurePosixPath(name).suffix.lower().lstrip(".")


def safe_filename(raw: str) -> str:
    """A plain, visible name for an uploaded file: no folders, no control, direction
    or reserved characters, no leading dot, at most NAME_MAX_BYTES, and a lower-case
    extension. ``C:\\Users\\me\\Q3 report?.PDF`` becomes ``Q3 report_.pdf``."""
    base = PurePosixPath(raw.replace("\\", "/")).name
    text = UNSAFE_NAME_CHARACTERS.sub("_", unicodedata.normalize("NFC", base))
    text = _SPACES.sub(" ", text).strip().lstrip(". ")
    original_suffix = PurePosixPath(text).suffix
    suffix = original_suffix.lower()
    stem = _fit(text[: len(text) - len(original_suffix)], NAME_MAX_BYTES - len(suffix.encode()))
    if not stem:
        raise ValidationFailed("The file needs a name.")
    return f"{stem}{suffix}"


def _fit(text: str, max_bytes: int) -> str:
    """``text`` cut to at most ``max_bytes`` of UTF-8, never inside a character,
    without the trailing dots and spaces some systems drop."""
    cut = text.encode("utf-8")[: max(max_bytes, 0)].decode("utf-8", errors="ignore")
    return cut.rstrip(". ")

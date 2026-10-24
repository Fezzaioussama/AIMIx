"""Artifact formats by extension (§5 O / §7 Strategy + Registry).

A new format is one renderer and one entry here, never another ``if``. Text
formats are saved as the agent wrote them; ``.docx`` and ``.pdf`` take Markdown
and lay it out. python-docx and ReportLab are third-party code fed model output,
so a failure inside them is re-raised as our own error (the §8 adapter case).
"""

from __future__ import annotations

import logging

from api.exceptions import UnsupportedFileType, ValidationFailed
from api.services.artifacts.contracts import Renderer, RenderOptions
from api.services.artifacts.docx_writer import render_docx
from api.services.artifacts.pdf_writer import render_pdf

logger = logging.getLogger(__name__)


def _utf8(content: str, options: RenderOptions) -> bytes:
    return content.encode("utf-8")


RENDERERS: dict[str, Renderer] = {
    ".txt": _utf8,
    ".md": _utf8,
    ".json": _utf8,
    ".csv": _utf8,
    ".html": _utf8,
    ".docx": render_docx,
    ".pdf": render_pdf,
}


def artifact_extensions() -> list[str]:
    return sorted(RENDERERS)


def render_artifact(extension: str, content: str, options: RenderOptions) -> bytes:
    """The bytes of a ``extension`` file (lower-case, with its dot) made from ``content``."""
    renderer = RENDERERS.get(extension)
    if renderer is None:
        raise UnsupportedFileType(
            f"'{extension or 'no extension'}' files cannot be saved. "
            f"Use one of: {', '.join(artifact_extensions())}."
        )
    try:
        return renderer(content, options)
    except Exception as cause:  # layout code can fail on any input; never a 500
        logger.info("artifacts.render_failed format=%s error=%s", extension, type(cause).__name__)
        raise ValidationFailed(
            f"The {extension} file could not be laid out from this content. "
            "Shorten very long table rows or lines and try again."
        ) from cause

"""Value objects shared by the artifact renderers (§7 DTO)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderOptions:
    """How documents look; every value comes from settings (§6)."""

    #: TrueType fonts for PDFs. A missing file falls back to a built-in font
    #: that covers Western European text only.
    pdf_font: Path
    pdf_bold_font: Path


#: The agent's text in, the file's bytes out.
Renderer = Callable[[str, RenderOptions], bytes]

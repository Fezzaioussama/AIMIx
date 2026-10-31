"""The generate_image tool's work: draw with Muse Image, save into the workspace.

The picture is a new JPEG of the user's workspace, so it shows on the Files page and
a .docx or .pdf the agent saves next can show it (``![alt](path)``). A refusal
reaches the model as a ToolException it can react to, never as an aborted run.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from langchain_core.tools import ToolException

from api.services.toolbox.workspace import LocalWorkspace
from llm.exceptions import LLMError
from llm.images import SIZES, ImageGenerator

logger = logging.getLogger(__name__)

JPEG_SUFFIX = ".jpg"


class ImageStudio:
    """Draws a picture and saves it as a new JPEG; never overwrites a file."""

    def __init__(self, generator: ImageGenerator, workspace: LocalWorkspace) -> None:
        self._generator = generator
        self._workspace = workspace

    def create(self, description: str, path: str, shape: str = "square") -> str:
        if shape not in SIZES:
            raise ToolException(f"shape must be one of: {', '.join(SIZES)}.")
        if not description.strip():
            raise ToolException("Describe the picture to draw.")
        try:
            target = str(PurePosixPath(path.strip()).with_suffix(JPEG_SUFFIX))
        except ValueError as cause:
            raise ToolException("Name the picture's file, e.g. images/hero.jpg.") from cause
        try:
            image = self._generator.generate(description, shape)
        except LLMError as cause:
            raise ToolException(
                "Muse Image could not draw this picture. Describe it differently and try again."
            ) from cause
        saved = self._workspace.save_bytes(target, image.jpeg)
        # Sizes only: the description is the user's content (§6).
        logger.info("images.generated shape=%s bytes=%d", shape, len(image.jpeg))
        return (
            f"Saved {saved}. To show it in a .docx or .pdf you save, put "
            f"![a short description]({saved}) on a line of its own."
        )

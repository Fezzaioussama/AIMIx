"""The find_objects tool's work: SAM 3.1 looks at a picture of the workspace, every
match is counted, and a copy with the matches boxed and numbered is saved for a
report. A refusal reaches the model as a ToolException, never as an aborted run.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath

from langchain_core.tools import ToolException
from PIL import Image, ImageDraw, ImageFont

from api.services.toolbox.workspace import LocalWorkspace
from llm.exceptions import LLMError
from llm.vision import Box, ObjectFinder

logger = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG"
#: The app's accent (sky-400), so a marked picture reads as AIMIx's.
MARK_COLOR = (56, 189, 248)
_NOT_A_NAME = re.compile(r"[^a-z0-9]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ObjectSpotter:
    """Finds, counts and marks every match of a noun phrase in a workspace picture."""

    def __init__(
        self,
        finder: ObjectFinder,
        workspace: LocalWorkspace,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._finder = finder
        self._workspace = workspace
        self._clock = clock

    def find(self, image_path: str, what: str) -> str:
        subject = what.strip()
        if not subject:
            raise ToolException("Name what to find, e.g. 'loaf of bread'.")
        data = self._workspace.read_picture(image_path)
        media_type = "image/png" if data.startswith(PNG_SIGNATURE) else "image/jpeg"
        try:
            boxes = self._finder.find(data, media_type, subject).boxes
        except LLMError as cause:
            raise ToolException("SAM 3.1 could not look at this picture. Try again.") from cause
        logger.info("vision.found matches=%d", len(boxes))
        if not boxes:
            return f"No {subject} found in {image_path}."
        marked = self._workspace.save_bytes(
            self._marked_path(image_path, subject), _marked(data, boxes)
        )
        return _report(image_path, subject, boxes, marked)

    def _marked_path(self, image_path: str, subject: str) -> str:
        """Next to the picture, named after what was found and when: never an existing file."""
        source = PurePosixPath(image_path)
        name = _NOT_A_NAME.sub("-", subject.lower()).strip("-")[:40] or "objects"
        stamp = self._clock().strftime("%Y%m%d-%H%M%S")
        return str(source.with_name(f"{source.stem}-{name}-{stamp}.jpg"))


def _marked(data: bytes, boxes: tuple[Box, ...]) -> bytes:
    """The picture as a JPEG with each box drawn and numbered in the order listed."""
    with Image.open(BytesIO(data)) as source:
        picture = source.convert("RGB")
    draw = ImageDraw.Draw(picture)
    line = max(2, round(max(picture.size) / 400))
    font = ImageFont.load_default(size=line * 9)
    for number, box in enumerate(boxes, start=1):
        draw.rectangle((box.x1, box.y1, box.x2, box.y2), outline=MARK_COLOR, width=line)
        label = (box.x1 + line * 2, box.y1 + line)
        draw.text(
            label, str(number), fill=MARK_COLOR, font=font, stroke_width=line, stroke_fill="black"
        )
    out = BytesIO()
    picture.save(out, "JPEG", quality=90)
    return out.getvalue()


def _report(image_path: str, subject: str, boxes: tuple[Box, ...], marked: str) -> str:
    matches = "1 match" if len(boxes) == 1 else f"{len(boxes)} matches"
    lines = [f'Found {matches} for "{subject}" in {image_path} (boxes in pixels):']
    lines += [
        f"{number}. ({box.x1}, {box.y1}) to ({box.x2}, {box.y2}), confidence {box.confidence:.0%}"
        for number, box in enumerate(boxes, start=1)
    ]
    lines.append(
        f"A copy with the boxes numbered is saved as {marked}; show it in a .docx or .pdf "
        f"with ![a short description]({marked}) on a line of its own."
    )
    return "\n".join(lines)

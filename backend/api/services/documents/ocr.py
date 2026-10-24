"""The OCR engine behind the OcrEngine port: Tesseract, through pytesseract (§7 Adapter).

``ocr_engine`` is called once, when the app starts. It returns None when OCR is
turned off, when the ``tesseract`` binary is missing, or when a configured
language is not installed, and logs which: readers then skip what needs OCR and
say so, instead of every upload failing on a misconfigured server.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

import pytesseract  # type: ignore[import-untyped]
from PIL import Image

from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents.contracts import OcrEngine
from config.settings import Settings

logger = logging.getLogger(__name__)

TESSERACT = "tesseract"


@dataclass(frozen=True)
class OcrConfig:
    enabled: bool
    #: Tesseract language codes joined by "+", e.g. "eng+fra".
    languages: str
    #: Bounds each page's recognition, and the language check at startup.
    timeout_seconds: float


def ocr_config(settings: Settings) -> OcrConfig:
    return OcrConfig(
        enabled=settings.document_ocr_enabled,
        languages=settings.document_ocr_languages,
        timeout_seconds=settings.document_ocr_timeout_seconds,
    )


class TesseractOcr:
    """Runs the tesseract binary once per page, killed past the timeout."""

    def __init__(self, languages: str, timeout_seconds: float) -> None:
        self._languages = languages
        self._timeout = timeout_seconds

    def read(self, image: Image.Image) -> str:
        try:
            text: str = pytesseract.image_to_string(
                image, lang=self._languages, timeout=self._timeout
            )
        # TesseractError is a RuntimeError too, so it is matched first.
        except (pytesseract.TesseractError, OSError, TypeError) as cause:
            logger.warning("documents.ocr_failed error=%s", type(cause).__name__)
            raise DocumentUnreadable("Text recognition (OCR) failed on this file.") from cause
        except RuntimeError as cause:  # how pytesseract reports its timeout
            raise OcrTimedOut(
                f"Text recognition (OCR) took longer than {self._timeout:g} seconds on a page."
            ) from cause
        return text.strip()


def ocr_engine(config: OcrConfig) -> OcrEngine | None:
    """Tesseract when OCR is on and can run here; else None, with the reason logged."""
    if not config.enabled:
        logger.info("documents.ocr status=disabled")
        return None
    problem = _tesseract_problem(config)
    if problem:
        logger.warning("documents.ocr status=unavailable reason=%s", problem)
        return None
    logger.info("documents.ocr status=ready languages=%s", config.languages)
    return TesseractOcr(config.languages, config.timeout_seconds)


def _tesseract_problem(config: OcrConfig) -> str | None:
    """Why Tesseract cannot read ``config.languages`` here, or None when it can."""
    if shutil.which(TESSERACT) is None:
        return "binary_missing"
    try:
        listing = subprocess.run(
            [TESSERACT, "--list-langs"],
            capture_output=True,
            check=True,
            text=True,
            timeout=config.timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as cause:
        return f"check_failed:{type(cause).__name__}"
    # The first line is a header; the rest are installed language codes.
    installed = {line.strip() for line in (listing.stdout + listing.stderr).splitlines()}
    missing = [code for code in config.languages.split("+") if code not in installed]
    return f"languages_missing:{'+'.join(missing)}" if missing else None

"""The documents' part of ``deps.py``: what reading an uploaded document or a web page
needs at the HTTP boundary (its limits, the OCR engine, the page downloader). Tests
swap these functions through ``app.dependency_overrides`` like any other dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from api.deps import AppSettings
from api.services.documents.contracts import ExtractionLimits, OcrEngine
from api.services.documents.extraction import extraction_limits
from api.services.documents.web_import import PageImporter, link_limits
from api.services.web_download import PageDownloader


def document_limits(settings: AppSettings) -> ExtractionLimits:
    """What one document extraction may cost, from settings."""
    return extraction_limits(settings)


DocumentLimits = Annotated[ExtractionLimits, Depends(document_limits)]


def document_ocr(request: Request) -> OcrEngine | None:
    """The OCR engine the app built at startup; None when OCR is off or not installed."""
    engine: OcrEngine | None = request.app.state.ocr
    return engine


DocumentOcr = Annotated[OcrEngine | None, Depends(document_ocr)]


def page_downloader(settings: AppSettings) -> PageDownloader:
    """Downloads the pages users read from a link; tests swap in a fake network."""
    return PageDownloader(settings.web_timeout_seconds, settings.document_url_max_seconds)


def page_importer(
    downloader: Annotated[PageDownloader, Depends(page_downloader)],
    limits: DocumentLimits,
    ocr: DocumentOcr,
    settings: AppSettings,
) -> PageImporter:
    return PageImporter(downloader, limits, ocr, link_limits(settings))


PageImports = Annotated[PageImporter, Depends(page_importer)]

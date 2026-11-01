"""Read a web page, or a PDF, Office file, picture or text file behind a link, into
run-input text the way an uploaded document is read (POST /documents/import-url).

The download is ``api.services.web_download``'s: public addresses only, every
redirect hop checked, WEB_TIMEOUT_SECONDS per request and DOCUMENT_URL_MAX_SECONDS
in all, and refused, never cut, past DOCUMENT_MAX_BYTES. At most
DOCUMENT_URL_MAX_CONCURRENT links are read at once in the process (each holds what it
downloaded until it is read). The media type picks the reader (SUFFIX_BY_MEDIA_TYPE,
§7 Strategy + Registry), and ``extraction.read_document`` reads the bytes with the
limits, OCR and reading slots of an upload, and the charset the Content-Type header
names, in a worker thread since it blocks. Stateless like an upload: nothing is
stored, and the URL is never logged (§6).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from functools import partial
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import anyio
import httpx

from api.exceptions import (
    DocumentTooLarge,
    DocumentUnreadable,
    DomainError,
    PageUnreachable,
    UnsupportedDocument,
    ValidationFailed,
)
from api.services.addresses import AddressNotAllowed, HostNotFound
from api.services.documents.contracts import (
    ExtractedDocument,
    ExtractionLimits,
    OcrEngine,
    ReadContext,
    SlotPool,
)
from api.services.documents.extraction import megabytes, read_document, with_notes
from api.services.documents.gate import extraction_slot
from api.services.documents.readers import READERS
from api.services.web_download import (
    Download,
    DownloadFailed,
    PageDownloader,
    UnusableUrl,
    UnwantedMediaType,
)
from config.settings import Settings

logger = logging.getLogger(__name__)

#: Media type -> the extension whose reader reads it; a new format is one entry (§5 O).
SUFFIX_BY_MEDIA_TYPE: dict[str, str] = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "text/tab-separated-values": ".tsv",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
}
#: Media types that say nothing of the format: the bytes, then the link's extension decide.
GENERIC_MEDIA_TYPES = frozenset({"", "application/octet-stream", "binary/octet-stream"})
PDF_SIGNATURE = b"%PDF-"
#: Formats a browser renders: one with too little text is built by JavaScript.
PAGE_FORMATS = frozenset({".html", ".htm"})
#: Answers that mean "not for you" rather than "not there".
REFUSING_STATUSES = frozenset({401, 403, 429})
#: A link never waits for a slot: waiting would hold up the event loop it downloads on.
NO_WAIT = 0.0

PUBLIC_ONLY = "AIMIx can only open public web pages."
UNSUPPORTED = "AIMIx can read web pages, PDF, Word, Excel, PowerPoint, images and text from a link."
BUILT_IN_BROWSER = (
    "This page builds its text in the browser, so AIMIx can't read it from the link. "
    "Copy the text into the box, or print the page to PDF and attach it."
)
REFUSED = (
    "This site didn't let AIMIx read the page (it may need a sign-in or block automated "
    "readers). Open it in your browser, save or print it as PDF, and attach the PDF."
)
TOO_SLOW = "The site took too long to answer. Try again, or save the page as PDF and attach it."
UNREACHABLE = "AIMIx couldn't reach this site."

#: What a failed download tells the user; the first match wins, anything else is
#: UNREACHABLE (§7 Strategy map, as api/services/errors.py does for providers).
FAILURES: tuple[tuple[tuple[type[Exception], ...], type[DomainError], str], ...] = (
    ((UnwantedMediaType,), UnsupportedDocument, UNSUPPORTED),
    ((HostNotFound,), PageUnreachable, UNREACHABLE),
    ((UnusableUrl, AddressNotAllowed, httpx.InvalidURL), ValidationFailed, PUBLIC_ONLY),
    ((TimeoutError, httpx.TimeoutException), PageUnreachable, TOO_SLOW),
)
#: Everything a download raises that is not a bug.
DOWNLOAD_ERRORS = (
    DownloadFailed,
    AddressNotAllowed,
    TimeoutError,
    httpx.HTTPError,
    httpx.InvalidURL,
)


def _site_answered(status: int) -> PageUnreachable:
    if status in REFUSING_STATUSES:
        return PageUnreachable(REFUSED)
    return PageUnreachable(f"AIMIx couldn't open this page (the site answered {status}).")


def _as_domain_error(cause: Exception) -> DomainError:
    if isinstance(cause, httpx.HTTPStatusError):
        return _site_answered(cause.response.status_code)
    for kinds, error, message in FAILURES:
        if isinstance(cause, kinds):
            return error(message)
    return PageUnreachable(UNREACHABLE)


def _readable(media_type: str) -> bool:
    return media_type in GENERIC_MEDIA_TYPES or media_type in SUFFIX_BY_MEDIA_TYPE


def _suffix(download: Download) -> str:
    """The extension of the reader for the download: by its media type, else a
    PDF by its signature, else the link's own extension."""
    if download.media_type not in GENERIC_MEDIA_TYPES:
        return SUFFIX_BY_MEDIA_TYPE[download.media_type]
    if download.body.startswith(PDF_SIGNATURE):
        return ".pdf"
    suffix = PurePosixPath(urlsplit(download.url).path).suffix.lower()
    if suffix not in READERS:
        raise UnsupportedDocument(UNSUPPORTED)
    return suffix


def _extract(
    download: Download, suffix: str, limits: ExtractionLimits, ocr: OcrEngine | None
) -> ExtractedDocument:
    """Blocks on a reading slot and the parsers: run it in a worker thread. Text is
    read in the charset the Content-Type header names, unless a byte order mark names
    another (``html_text``'s rules)."""
    context = ReadContext(limits, ocr, charset=download.charset)
    return with_notes(read_document(f"page{suffix}", download.body, context))


def _log(outcome: str, started: float, document: ExtractedDocument | None, size: int) -> None:
    # Never the URL: it may hold a token, or say what the user is working on (§6).
    logger.info(
        "documents.url_imported outcome=%s format=%s bytes=%d chars=%d duration_ms=%d",
        outcome,
        document.format if document else "-",
        size,
        document.characters if document else 0,
        (time.monotonic() - started) * 1000,
    )


@dataclass(frozen=True)
class LinkLimits:
    """What reading links may cost, from settings (§6)."""

    #: DOCUMENT_URL_MIN_TEXT_CHARS: a web page with less text is built by JavaScript.
    min_text_chars: int
    #: DOCUMENT_URL_MAX_CONCURRENT: links downloaded and read at once in the process,
    #: each holding what it downloaded until it is read.
    max_links: int


def link_limits(settings: Settings) -> LinkLimits:
    return LinkLimits(settings.document_url_min_text_chars, settings.document_url_max_concurrent)


@dataclass(frozen=True)
class PageImporter:
    """Reads what a link holds into run-input text (one per request, from deps.py)."""

    downloader: PageDownloader
    limits: ExtractionLimits
    ocr: OcrEngine | None
    links: LinkLimits

    async def read(self, url: str) -> ExtractedDocument:
        """The text at ``url``, named after the page the link ended at. Raises the
        document errors of an upload, ValidationFailed for a link that is not a
        public web address, PageUnreachable when the site does not hand it over, and
        DocumentReadersBusy when ``links.max_links`` links are already being read."""
        started = time.monotonic()
        try:
            with extraction_slot(self.links.max_links, NO_WAIT, SlotPool.LINKS):
                download = await self._download(url)
                document = await self._read(download)
        except DomainError as error:
            _log(error.code, started, None, 0)
            raise
        _log("ok", started, document, len(download.body))
        return replace(document, filename=download.url)

    async def _download(self, url: str) -> Download:
        try:
            download = await self.downloader.download(url, self.limits.max_bytes, _readable)
        except DOWNLOAD_ERRORS as cause:
            raise _as_domain_error(cause) from cause
        if download.truncated:
            raise DocumentTooLarge(
                f"What this link holds is larger than the {megabytes(self.limits.max_bytes)} limit."
            )
        return download

    async def _read(self, download: Download) -> ExtractedDocument:
        suffix = _suffix(download)
        extract = partial(_extract, download, suffix, self.limits, self.ocr)
        if suffix not in PAGE_FORMATS:
            return await anyio.to_thread.run_sync(extract)
        try:
            document = await anyio.to_thread.run_sync(extract)
        except DocumentUnreadable as cause:  # not a word of text
            raise DocumentUnreadable(BUILT_IN_BROWSER) from cause
        if document.characters < self.links.min_text_chars:
            raise DocumentUnreadable(BUILT_IN_BROWSER)
        return document

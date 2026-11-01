"""Bounded workspace access for built-in agent tools (§7 Adapter).

Where a path may lead, overwrites and the storage quota are ``WorkspaceStorage``'s
rules, the same ones the Files page follows. This gateway adds what a model needs
on top: text in pages it can read on through, search, CSV rows, PDF and Word files
read as text (scanned pages by OCR), and artifacts saved in real document formats.
A refusal reaches the model as a ToolException it can react to, never as an
aborted run.
"""

from __future__ import annotations

import codecs
import csv
import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

from langchain_core.tools import ToolException
from PIL import Image

from api.exceptions import DomainError, FileTooLarge
from api.services.artifacts.contracts import RenderOptions
from api.services.artifacts.registry import render_artifact
from api.services.documents.contracts import ExtractionLimits, ReadContext
from api.services.documents.extraction import (
    extract_document,
    megabytes,
    omission_notes,
    read_document,
)
from api.services.documents.pdf import page_count
from api.services.documents.scans import no_such_page
from api.services.files.storage import WorkspaceStorage
from api.services.toolbox.config import WorkspaceOptions

#: Read and searched as they are; any other file is read through the document
#: readers (PDF, Word, ...), which refuse what they cannot read.
TEXT_SUFFIXES = frozenset({".csv", ".html", ".json", ".md", ".txt", ".yaml", ".yml"})
CSV_SUFFIX = ".csv"
#: Read in its own whole pages; any other file in pages of the output limit.
PDF_SUFFIX = ".pdf"
#: The pictures a saved .docx or .pdf may show: what python-docx and ReportLab both embed.
PICTURE_FORMATS = ("PNG", "JPEG")


@dataclass(frozen=True)
class WorkspaceLimits:
    max_file_bytes: int
    max_output_chars: int
    search_max_files: int
    search_max_results: int
    csv_max_rows: int
    #: What reading one PDF or Word file may cost: the run-document limits.
    documents: ExtractionLimits


@dataclass(frozen=True)
class FilePages:
    """What one read shows of a file: its pages ``first`` to ``last`` of ``total``.
    A PDF's pages are its own; any other file is cut into pages of the output limit."""

    text: str
    first: int
    last: int
    total: int


def _spreadsheet_safe(path: str, content: bytes, options: RenderOptions) -> bytes:
    """A ``.csv`` with every cell a spreadsheet would run as a formula made text,
    as ``save_artifact`` saves one (``artifacts.csv_writer``); any other file as
    it is. A CSV with nothing to change keeps its bytes; a rewritten one is UTF-8,
    keeping its byte-order mark. One that cannot be checked is refused."""
    if Path(path).suffix.lower() != CSV_SUFFIX:
        return content
    bom = codecs.BOM_UTF8 if content.startswith(codecs.BOM_UTF8) else b""
    body = content[len(bom) :]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:  # Latin-1 reads every byte, so no formula stays hidden
        text = body.decode("latin-1")
    rendered = render_artifact(CSV_SUFFIX, text, options)
    return content if rendered == text.encode("utf-8") else bom + rendered


def _is_picture(data: bytes, max_pixels: int) -> bool:
    """Whether ``data`` is a PNG or JPEG of at most ``max_pixels``, from its header."""
    try:
        with Image.open(BytesIO(data), formats=PICTURE_FORMATS) as image:
            return image.width * image.height <= max_pixels
    except (OSError, Image.DecompressionBombError):  # not a picture, or a pixel bomb
        return False


@contextmanager
def _tool_errors() -> Iterator[None]:
    """Hand a domain refusal (a bad path, a full quota, ...) to the model."""
    try:
        yield
    except DomainError as cause:
        raise ToolException(cause.detail) from cause


class LocalWorkspace:
    """Gateway that confines every file operation to one user's directory."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        limits: WorkspaceLimits,
        render: RenderOptions,
        options: WorkspaceOptions = WorkspaceOptions(),
    ) -> None:
        self._storage = storage
        self._limits = limits
        self._render = render
        self._ocr = options.ocr
        self._drafts_since = options.drafts_since

    def list_files(self, directory: str = ".") -> str:
        base = self._resolve(directory, directory=True)
        files: list[str] = []
        for path, _ in self._storage.files(base):
            files.append(self._storage.relative_path(path))
            if len(files) >= self._limits.search_max_results:
                break
        return "\n".join(sorted(files)) or "No files found."

    def read_file(self, path: str, start_page: int = 1) -> FilePages:
        """A file's text from page ``start_page`` on, as much as one read shows."""
        if start_page < 1:
            raise ToolException("start_page counts from 1.")
        target = self._resolve(path)
        suffix = target.suffix.lower()
        if suffix == PDF_SUFFIX:
            return self._pdf_pages(target, start_page)
        text = self._whole_text(target) if suffix in TEXT_SUFFIXES else self._document_text(target)
        return _page_of(text, start_page, self._limits.max_output_chars)

    def search_files(self, query: str, directory: str = ".") -> str:
        needle = query.strip().casefold()
        if not needle:
            raise ToolException("The search query cannot be empty.")
        base = self._resolve(directory, directory=True)
        matches: list[str] = []
        for path in self._searchable_files(base):
            matches.extend(self._matching_lines(path, needle))
            if len(matches) >= self._limits.search_max_results:
                break
        return "\n".join(matches[: self._limits.search_max_results]) or "No matches found."

    def read_csv(self, path: str) -> str:
        target = self._resolve(path)
        if target.suffix.lower() != ".csv":
            raise ToolException("The requested file must have a .csv extension.")
        text = self._bounded_text(target)
        try:
            rows = list(csv.DictReader(text.splitlines()))[: self._limits.csv_max_rows]
        except csv.Error as cause:
            raise ToolException("The CSV file could not be parsed.") from cause
        return json.dumps(rows, ensure_ascii=False)[: self._limits.max_output_chars]

    def save_artifact(self, path: str, content: str) -> str:
        """Saves a new file, or replaces this run's own draft of it; a PDF's reply
        gives its page count, so an agent asked for one page can tell."""
        with _tool_errors():
            draft = self._is_draft(path)
            target = self._storage.writable(path, replace=draft)
            self._check_artifact_size(len(content.encode("utf-8", errors="replace")))
            options = replace(self._render, pictures=self._picture)
            data = render_artifact(target.suffix.lower(), content, options)
            saved = self._store(path, data, overwrite=draft)
            return f"{'Replaced' if draft else 'Saved'} {saved}{_length(target.suffix, data)}"

    def read_bytes(self, path: str) -> bytes:
        """Any visible file's raw content, within the file size limit. The storage
        never follows a link, so a link to a hidden file is not read either."""
        target = self._resolve(path)
        try:
            return self._within_size_limit(target).read_bytes()
        except OSError as cause:
            raise ToolException("The file could not be read.") from cause

    def save_bytes(self, path: str, content: bytes) -> str:
        """Save a new file of any type; returns its workspace-relative path. A
        ``.csv`` is made safe to open in a spreadsheet first, like an artifact."""
        with _tool_errors():
            return self._store(path, _spreadsheet_safe(path, content, self._render))

    def _store(self, path: str, data: bytes, *, overwrite: bool = False) -> str:
        """Write a file within the file limit and the quota; an existing one only
        with ``overwrite``."""
        self._check_artifact_size(len(data))
        try:
            return self._storage.relative_path(self._storage.save(path, data, replace=overwrite))
        except OSError as cause:
            raise ToolException("The artifact could not be saved.") from cause

    def _is_draft(self, path: str) -> bool:
        """Whether ``path`` is a file saved since this run started: its own draft."""
        since, changed = self._drafts_since, self._storage.modified(path)
        return since is not None and changed is not None and changed >= since

    def _resolve(self, relative: str, *, directory: bool = False) -> Path:
        with _tool_errors():
            return self._storage.existing(relative, directory=directory)

    def _check_artifact_size(self, size: int) -> None:
        if size > self._limits.max_file_bytes:
            limit = megabytes(self._limits.max_file_bytes)
            raise FileTooLarge(f"The artifact is larger than the {limit} file limit.")

    def _searchable_files(self, base: Path) -> list[Path]:
        files: list[Path] = []
        for path, _ in self._storage.files(base):
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
            if len(files) >= self._limits.search_max_files:
                break
        return sorted(files)

    def _matching_lines(self, path: Path, needle: str) -> list[str]:
        try:
            text = self._bounded_text(path)
        except ToolException:
            return []
        relative = self._storage.relative_path(path)
        return [
            f"{relative}:{number}: {line.strip()}"
            for number, line in enumerate(text.splitlines(), start=1)
            if needle in line.casefold()
        ]

    def _bounded_text(self, path: Path) -> str:
        return self._whole_text(path)[: self._limits.max_output_chars]

    def _whole_text(self, path: Path) -> str:
        try:
            return self._within_size_limit(path).read_text(encoding="utf-8")
        except UnicodeError as cause:
            raise ToolException("The file is not valid UTF-8 text.") from cause
        except OSError as cause:
            raise ToolException("The file could not be read.") from cause

    def _within_size_limit(self, path: Path) -> Path:
        if path.stat().st_size > self._limits.max_file_bytes:
            raise ToolException("The file is larger than the configured limit.")
        return path

    def read_picture(self, path: str) -> bytes:
        """A PNG or JPEG of the workspace, within the file and pixel limits."""
        data = self.read_bytes(path)
        if not _is_picture(data, self._limits.documents.max_image_pixels):
            raise ToolException("The file is not a PNG or JPEG picture of a size that can be read.")
        return data

    def _picture(self, path: str) -> bytes | None:
        """A picture for a document to show, or None for anything else (a web address
        is never fetched)."""
        try:
            return self.read_picture(path)
        except ToolException:
            return None

    def _pdf_pages(self, path: Path, start_page: int) -> FilePages:
        """A PDF's whole pages from ``start_page`` on, as many as the output limit and
        OCR's budget allow; the pages before it are not read, nor OCR'd, again."""
        cap = self._limits.max_output_chars
        limits = replace(self._limits.documents, max_chars=cap)
        context = ReadContext(limits, self._ocr, first_page=start_page, read_on=True)
        with _tool_errors():
            document = read_document(path.name, self._document_bytes(path), context)
        text = document.text
        if document.clipped:
            text += (
                f"\n\n[Page {start_page} is longer than {cap:,} characters: "
                "the rest of it is not shown.]"
            )
        last = document.last_page or start_page
        return FilePages(
            text + omission_notes(document.omissions), start_page, last, document.pages or last
        )

    def _document_text(self, path: Path) -> str:
        """A Word, Excel, PowerPoint, HTML or image file as text, up to the run-document
        limit, ending with a note on whatever was left out."""
        limits = self._limits.documents
        with _tool_errors():
            return extract_document(path.name, self._document_bytes(path), limits, self._ocr).text

    def _document_bytes(self, path: Path) -> bytes:
        try:
            with path.open("rb") as handle:
                # One byte past the cap is enough for the reader to refuse the file.
                return handle.read(self._limits.documents.max_bytes + 1)
        except OSError as cause:
            raise ToolException("The file could not be read.") from cause


def _length(suffix: str, data: bytes) -> str:
    """A saved PDF's page count, as save_artifact's reply ends: " (2 pages)"."""
    if suffix.lower() != PDF_SUFFIX:
        return ""
    pages = page_count(data)
    return f" ({pages} page{'' if pages == 1 else 's'})"


def _page_of(text: str, number: int, size: int) -> FilePages:
    """Page ``number`` of ``text`` cut into pages of ``size`` characters."""
    total = max(1, math.ceil(len(text) / size))
    if number > total:
        raise ToolException(no_such_page("This file", total, number))
    return FilePages(text[(number - 1) * size : number * size], number, number, total)

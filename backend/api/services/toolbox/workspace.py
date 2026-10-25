"""Bounded workspace access for built-in agent tools (§7 Adapter).

Where a path may lead, overwrites and the storage quota are ``WorkspaceStorage``'s
rules, the same ones the Files page follows. This gateway adds what a model needs
on top: bounded text, search, CSV rows, PDF and Word files read as text, and
artifacts saved in real document formats. A refusal reaches the model as a
ToolException it can react to, never as an aborted run.
"""

from __future__ import annotations

import codecs
import csv
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from langchain_core.tools import ToolException

from api.exceptions import DomainError, FileTooLarge
from api.services.artifacts.contracts import RenderOptions
from api.services.artifacts.registry import render_artifact
from api.services.documents.contracts import ExtractionLimits
from api.services.documents.extraction import extract_document, megabytes
from api.services.files.storage import WorkspaceStorage

#: Read and searched as they are; any other file is read through the document
#: readers (PDF, Word, ...), which refuse what they cannot read.
TEXT_SUFFIXES = frozenset({".csv", ".html", ".json", ".md", ".txt", ".yaml", ".yml"})
CSV_SUFFIX = ".csv"


@dataclass(frozen=True)
class WorkspaceLimits:
    max_file_bytes: int
    max_output_chars: int
    search_max_files: int
    search_max_results: int
    csv_max_rows: int
    #: What reading one PDF or Word file may cost: the run-document limits.
    documents: ExtractionLimits


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
        self, storage: WorkspaceStorage, limits: WorkspaceLimits, render: RenderOptions
    ) -> None:
        self._storage = storage
        self._limits = limits
        self._render = render

    def list_files(self, directory: str = ".") -> str:
        base = self._resolve(directory, directory=True)
        files: list[str] = []
        for path, _ in self._storage.files(base):
            files.append(self._storage.relative_path(path))
            if len(files) >= self._limits.search_max_results:
                break
        return "\n".join(sorted(files)) or "No files found."

    def read_file(self, path: str) -> str:
        target = self._resolve(path)
        if target.suffix.lower() in TEXT_SUFFIXES:
            return self._bounded_text(target)
        return self._document_text(target)

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
        with _tool_errors():
            target = self._storage.writable(path)
            self._check_artifact_size(len(content.encode("utf-8", errors="replace")))
            data = render_artifact(target.suffix.lower(), content, self._render)
            return f"Saved {self._store(path, data)}"

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

    def _store(self, path: str, data: bytes) -> str:
        """Write a new file within the file limit and the quota, never replacing one."""
        self._check_artifact_size(len(data))
        try:
            return self._storage.relative_path(self._storage.save(path, data))
        except OSError as cause:
            raise ToolException("The artifact could not be saved.") from cause

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
        try:
            text = self._within_size_limit(path).read_text(encoding="utf-8")
            return text[: self._limits.max_output_chars]
        except UnicodeError as cause:
            raise ToolException("The file is not valid UTF-8 text.") from cause
        except OSError as cause:
            raise ToolException("The file could not be read.") from cause

    def _within_size_limit(self, path: Path) -> Path:
        if path.stat().st_size > self._limits.max_file_bytes:
            raise ToolException("The file is larger than the configured limit.")
        return path

    def _document_text(self, path: Path) -> str:
        """A PDF, Word or other document as text, cut at the output limit."""
        limits = replace(self._limits.documents, max_chars=self._limits.max_output_chars)
        try:
            with path.open("rb") as handle:
                # One byte past the cap is enough for the reader to refuse the file.
                data = handle.read(limits.max_bytes + 1)
        except OSError as cause:
            raise ToolException("The file could not be read.") from cause
        with _tool_errors():
            return extract_document(path.name, data, limits).text

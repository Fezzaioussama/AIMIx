"""Bounded local workspace access for built-in agent tools."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import ToolException

TEXT_SUFFIXES = frozenset({".csv", ".html", ".json", ".md", ".txt", ".yaml", ".yml"})
ARTIFACT_SUFFIXES = frozenset({".csv", ".json", ".md", ".txt"})


@dataclass(frozen=True)
class WorkspaceLimits:
    max_file_bytes: int
    max_output_chars: int
    search_max_files: int
    search_max_results: int
    csv_max_rows: int


class LocalWorkspace:
    """Gateway that confines every file operation to one configured directory."""

    def __init__(self, root: Path, limits: WorkspaceLimits) -> None:
        self._root = root.resolve()
        self._limits = limits

    def list_files(self, directory: str = ".") -> str:
        base = self._resolve(directory, directory=True)
        files: list[str] = []
        for path in base.rglob("*"):
            if path.is_file() and not path.is_symlink() and self._visible(path):
                files.append(str(path.relative_to(self._root)))
            if len(files) >= self._limits.search_max_results:
                break
        return "\n".join(sorted(files)) or "No files found."

    def read_file(self, path: str) -> str:
        target = self._resolve(path)
        if target.suffix.lower() not in TEXT_SUFFIXES:
            raise ToolException(
                "Only text, JSON, YAML, HTML, Markdown, and CSV files are readable."
            )
        return self._bounded_text(target)

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
        target = self._resolve_new(path)
        if target.suffix.lower() not in ARTIFACT_SUFFIXES:
            raise ToolException("Artifacts must use .txt, .md, .json, or .csv.")
        encoded = content.encode("utf-8")
        if len(encoded) > self._limits.max_file_bytes:
            raise ToolException("The artifact is larger than the configured file limit.")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", errors="strict", newline="") as artifact:
                artifact.write(content)
        except FileExistsError as cause:
            raise ToolException("The artifact already exists; choose a new path.") from cause
        except OSError as cause:
            raise ToolException("The artifact could not be saved.") from cause
        return f"Saved {target.relative_to(self._root)}"

    def _resolve(self, relative: str, *, directory: bool = False) -> Path:
        target = self._safe_path(relative).resolve()
        missing = not target.exists()
        wrong_type = (directory and not target.is_dir()) or (not directory and not target.is_file())
        if missing or wrong_type:
            raise ToolException("The requested workspace path does not exist.")
        return target

    def _resolve_new(self, relative: str) -> Path:
        target = self._safe_path(relative)
        parent = target.parent.resolve()
        self._within_root(parent)
        if target.exists():
            raise ToolException("The artifact already exists; choose a new path.")
        return target

    def _safe_path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or any(part.startswith(".") for part in candidate.parts):
            raise ToolException("Use a visible path relative to the workspace.")
        target = self._root / candidate
        self._within_root(target.resolve(strict=False))
        return target

    def _within_root(self, target: Path) -> None:
        if not target.is_relative_to(self._root):
            raise ToolException("The requested path is outside the workspace.")

    def _visible(self, path: Path) -> bool:
        return not any(part.startswith(".") for part in path.relative_to(self._root).parts)

    def _searchable_files(self, base: Path) -> list[Path]:
        files: list[Path] = []
        for path in base.rglob("*"):
            eligible = (
                path.is_file()
                and not path.is_symlink()
                and self._visible(path)
                and path.suffix.lower() in TEXT_SUFFIXES
            )
            if eligible:
                files.append(path)
            if len(files) >= self._limits.search_max_files:
                break
        return sorted(files)

    def _matching_lines(self, path: Path, needle: str) -> list[str]:
        try:
            text = self._bounded_text(path)
        except ToolException:
            return []
        relative = path.relative_to(self._root)
        return [
            f"{relative}:{number}: {line.strip()}"
            for number, line in enumerate(text.splitlines(), start=1)
            if needle in line.casefold()
        ]

    def _bounded_text(self, path: Path) -> str:
        try:
            if path.stat().st_size > self._limits.max_file_bytes:
                raise ToolException("The file is larger than the configured limit.")
            return path.read_text(encoding="utf-8")[: self._limits.max_output_chars]
        except UnicodeError as cause:
            raise ToolException("The file is not valid UTF-8 text.") from cause
        except OSError as cause:
            raise ToolException("The file could not be read.") from cause

"""One user's private directory, shared by their agents and the Files page (§7 Gateway).

Both go through the same rules here, never a copy of them: a path is relative and
visible (not absolute, no ``..``, nothing hidden), stays inside the directory and
never passes through a link; a new name holds no control, direction or reserved
character; a write replaces a file only when asked to, and never takes the user
past their storage quota, in bytes or in files and folders. Failures are domain
errors (§2): the HTTP layer returns them as they are, and the agent tools hand
them to the model.
"""

from __future__ import annotations

import os
import re
import stat
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath
from uuid import uuid4

from api.exceptions import FileAlreadyExists, NotFound, StorageQuotaExceeded, ValidationFailed
from api.services.documents.extraction import megabytes

#: Longest file or folder name most filesystems store, in UTF-8 bytes.
NAME_MAX_BYTES = 255
#: Longest path accepted below the root, well inside the system's own limit.
PATH_MAX_BYTES = 1024
#: Characters no file or folder name keeps: controls (C0 and C1, line breaks among
#: them), the line and paragraph separators, the direction marks and overrides
#: that make a name read otherwise than it is stored, and the separators and
#: wildcards some operating system reserves. An upload has them replaced
#: (names.safe_filename); a path an agent chooses is refused.
UNSAFE_NAME_CHARACTERS = re.compile(
    r"[\x00-\x1f\x7f-\x9f"
    r"\N{ARABIC LETTER MARK}\N{LEFT-TO-RIGHT MARK}\N{RIGHT-TO-LEFT MARK}"
    r"\N{LINE SEPARATOR}-\N{RIGHT-TO-LEFT OVERRIDE}"
    r"\N{LEFT-TO-RIGHT ISOLATE}-\N{POP DIRECTIONAL ISOLATE}"
    r'/\\:*?"<>|]+'
)
#: A replacement is first written to a hidden file named like this beside its target.
_STAGED = re.compile(r"\.upload-[0-9a-f]{32}\.part")
#: A staged file lives as long as one write takes; one this old was left by a crash,
#: and is removed the next time the quota is counted.
_STALE_STAGED_SECONDS = 3600


def user_workspace_dir(root: Path, user_id: int) -> Path:
    """The private directory of one account, below AGENT_WORKSPACE_DIR."""
    return root / f"user-{user_id}"


@dataclass(frozen=True)
class WorkspaceUsage:
    """What the quota counts: the bytes of every file, and every file and folder."""

    bytes: int
    entries: int


class WorkspaceStorage:
    """Confined access to one directory, holding at most ``max_total_bytes`` in at
    most ``max_files`` files and folders."""

    def __init__(self, root: Path, max_total_bytes: int, max_files: int) -> None:
        self._root = root.resolve()
        self._max_total_bytes = max_total_bytes
        self._max_files = max_files

    @property
    def root(self) -> Path:
        return self._root

    @property
    def max_total_bytes(self) -> int:
        return self._max_total_bytes

    def prepare(self) -> None:
        """Create the directory, readable by the server's own user only."""
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._root.chmod(0o700)

    def relative_path(self, path: Path) -> str:
        """``path`` as the user names it: relative, with ``/`` separators."""
        return path.relative_to(self._root).as_posix()

    def existing(self, relative: str, *, directory: bool = False) -> Path:
        """The file (or directory) at ``relative``; NotFound when there is none."""
        target = self._confined(relative)
        found = target.is_dir() if directory else _regular_stat(target) is not None
        if not found:
            raise NotFound(f"'{relative}' does not exist in the workspace.")
        return target

    def files(self, base: Path | None = None) -> Iterator[tuple[Path, os.stat_result]]:
        """Visible regular files below ``base`` (the root by default) and their
        status. Hidden names are skipped; links are neither listed nor followed."""
        for path in (base or self._root).rglob("*"):
            info = _regular_stat(path)
            if info is not None and self._visible(path):
                yield path, info

    def usage(self) -> WorkspaceUsage:
        """What the quota counts, in one pass: hidden files too (a replacement being
        staged), so nothing escapes it. A staged file a crash left is removed."""
        size = entries = 0
        for path in self._root.rglob("*"):
            try:
                info = path.lstat()
            except OSError:  # gone meanwhile
                continue
            if _stale_staged(path, info):
                path.unlink(missing_ok=True)
                continue
            entries += 1
            size += info.st_size if stat.S_ISREG(info.st_mode) else 0
        return WorkspaceUsage(size, entries)

    def writable(self, relative: str, *, replace: bool = False) -> Path:
        """Where ``relative`` would be written. Refused when a name in it holds an
        unsafe character, or when it would replace a folder, or a file without
        ``replace``."""
        target = self._confined(relative)
        if any(UNSAFE_NAME_CHARACTERS.search(name) for name in PurePath(relative).parts):
            raise ValidationFailed(
                "File and folder names cannot contain control characters, line breaks, "
                'text-direction marks or any of \\ : * ? " < > |.'
            )
        if target.is_dir():
            raise ValidationFailed(f"'{relative}' is a folder; choose a file name.")
        if not replace and target.exists():
            raise _taken(relative)
        return target

    def save(self, relative: str, data: bytes, *, replace: bool = False) -> Path:
        """Store ``data`` at ``relative`` within the quota; see ``writable``.

        Counting the quota walks every file, so each save counts it once: before
        replacing a file, or once a new file is on disk."""
        target = self.writable(relative, replace=replace)
        self.prepare()
        current = _regular_stat(target)
        if replace and current is not None:
            self._ensure_room(self.usage(), len(data) - current.st_size, adds_entries=False)
            _swap_in(target, data)
        else:
            self._create(target, data, relative)
        return target

    def delete(self, relative: str) -> None:
        target = self.existing(relative)
        try:
            target.unlink()
        except FileNotFoundError as cause:  # deleted meanwhile
            raise NotFound(f"'{relative}' does not exist in the workspace.") from cause
        self._prune(target.parent)

    def _confined(self, relative: str) -> Path:
        """``relative`` below the root, refusing every path a user may not reach."""
        candidate = PurePath(relative)
        hidden = any(part.startswith(".") for part in candidate.parts)
        if candidate.is_absolute() or hidden or not _storable(relative):
            raise ValidationFailed("Use a visible path relative to the workspace.")
        target = self._root / candidate
        resolved = target.resolve()
        if not resolved.is_relative_to(self._root):
            raise ValidationFailed("The requested path is outside the workspace.")
        if resolved != target:
            raise ValidationFailed("Links are not followed in the workspace.")
        return target

    def _visible(self, path: Path) -> bool:
        return not any(part.startswith(".") for part in path.relative_to(self._root).parts)

    def _ensure_room(
        self, usage: WorkspaceUsage, extra_bytes: int, *, adds_entries: bool = True
    ) -> None:
        if usage.bytes + extra_bytes > self._max_total_bytes:
            raise StorageQuotaExceeded(
                f"Your files would use more than the {megabytes(self._max_total_bytes)} "
                "storage limit. Delete some files first."
            )
        if adds_entries and usage.entries > self._max_files:
            raise StorageQuotaExceeded(
                f"Your workspace would hold more than {self._max_files:,} files and "
                "folders. Delete some files first."
            )

    def _create(self, target: Path, data: bytes, relative: str) -> None:
        """Write a new file, then count the quota with it (and any folder made for
        it) on disk. Of two writes that each fit alone, at least the later to
        finish sees the other and removes itself, so together they never stay
        over the limit."""
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = target.open("xb")
        except FileExistsError as cause:
            raise _taken(relative) from cause
        kept = False
        try:
            with handle:
                handle.write(data)
            self._ensure_room(self.usage(), 0)
            kept = True
        finally:
            if not kept:
                target.unlink(missing_ok=True)
                self._prune(target.parent)

    def _prune(self, directory: Path) -> None:
        """Remove the folders a deletion or a refused write left empty, up to the root."""
        while directory != self._root and directory.is_relative_to(self._root):
            try:
                directory.rmdir()
            except OSError:  # not empty
                return
            directory = directory.parent


def _taken(relative: str) -> FileAlreadyExists:
    return FileAlreadyExists(f"'{relative}' already exists; choose a new name.")


def _storable(relative: str) -> bool:
    """Text a filesystem can store: no NUL byte, no unpaired surrogate, no name
    longer than NAME_MAX_BYTES and no path longer than PATH_MAX_BYTES."""
    try:
        encoded = relative.encode("utf-8")
    except UnicodeEncodeError:
        return False
    names = PurePath(relative).parts
    return (
        b"\x00" not in encoded
        and len(encoded) <= PATH_MAX_BYTES
        and all(len(name.encode("utf-8")) <= NAME_MAX_BYTES for name in names)
    )


def _regular_stat(path: Path) -> os.stat_result | None:
    """The status of ``path`` when it is a regular file itself, not a link to one."""
    try:
        info = path.lstat()
    except OSError:  # gone meanwhile, or not a usable name
        return None
    return info if stat.S_ISREG(info.st_mode) else None


def _stale_staged(path: Path, info: os.stat_result) -> bool:
    """A staged replacement that no write will finish any more."""
    return (
        stat.S_ISREG(info.st_mode)
        and _STAGED.fullmatch(path.name) is not None
        and time.time() - info.st_mtime > _STALE_STAGED_SECONDS
    )


def _swap_in(target: Path, data: bytes) -> None:
    """Replace ``target`` in one step, so a reader sees the old file or the new one.
    The staged copy is hidden, so nobody lists or reads it meanwhile; the quota
    counts it."""
    staged = target.with_name(f".upload-{uuid4().hex}.part")
    try:
        staged.write_bytes(data)
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)

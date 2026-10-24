"""The Files page: list, download, upload and delete one user's files (§2 service).

Paths, links, overwrites and the quota belong to ``WorkspaceStorage``; this module
adds what only uploads by people need (a safe name, an extension allowlist and a
size cap per file) and the details a listing or a download shows. Never logs a
file's name or content (§6).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from api.exceptions import FileTooLarge, UnsupportedFileType, ValidationFailed
from api.services.documents.extraction import megabytes
from api.services.files.names import file_type, media_type, safe_filename
from api.services.files.storage import WorkspaceStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadPolicy:
    """What the Files page accepts; every value comes from settings (§6)."""

    max_file_bytes: int
    #: Lower-case extensions with their dot, e.g. ``.pdf``.
    allowed_extensions: frozenset[str]


@dataclass(frozen=True)
class Upload:
    """One uploaded file as the browser named it. ``data`` may hold one byte
    past the cap: that is how an oversized file is recognised unread."""

    filename: str
    data: bytes


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    modified_at: datetime
    #: Lower-case extension without the dot, e.g. ``pdf``.
    type: str


@dataclass(frozen=True)
class FileListing:
    """The files, newest first, with the limits the page shows next to them."""

    files: list[FileEntry]
    used_bytes: int
    quota_bytes: int
    max_file_bytes: int
    allowed_extensions: list[str]


@dataclass(frozen=True)
class FileDownload:
    location: Path
    filename: str
    media_type: str


def list_files(storage: WorkspaceStorage, policy: UploadPolicy) -> FileListing:
    entries = [_entry(storage, path, info) for path, info in storage.files()]
    entries.sort(key=lambda entry: (-entry.modified_at.timestamp(), entry.path))
    return FileListing(
        files=entries,
        used_bytes=sum(entry.size for entry in entries),
        quota_bytes=storage.max_total_bytes,
        max_file_bytes=policy.max_file_bytes,
        allowed_extensions=sorted(policy.allowed_extensions),
    )


def download(storage: WorkspaceStorage, path: str) -> FileDownload:
    target = storage.existing(path)
    return FileDownload(target, target.name, media_type(target.name))


def upload(
    storage: WorkspaceStorage, uploads: list[Upload], policy: UploadPolicy, *, replace: bool
) -> list[FileEntry]:
    """Store every upload under a safe name. Names, types and sizes are checked
    for all files before any is written; conflicts and the quota are checked as
    each is saved, so a refusal there keeps the files saved before it."""
    named = [(_accepted_name(item, policy), item.data) for item in uploads]
    if len({name for name, _ in named}) != len(named):
        raise ValidationFailed("Two of the files have the same name.")
    saved = [storage.save(name, data, replace=replace) for name, data in named]
    logger.info(
        "files.uploaded owner=%s count=%d bytes=%d replace=%s",
        storage.root.name,
        len(saved),
        sum(len(data) for _, data in named),
        replace,
    )
    return [_entry(storage, path, path.stat()) for path in saved]


def delete(storage: WorkspaceStorage, path: str) -> None:
    storage.delete(path)
    logger.info("files.deleted owner=%s", storage.root.name)


def _accepted_name(item: Upload, policy: UploadPolicy) -> str:
    name = safe_filename(item.filename)
    suffix = PurePosixPath(name).suffix
    if suffix not in policy.allowed_extensions:
        accepted = ", ".join(sorted(policy.allowed_extensions))
        kind = f"'{suffix}' files" if suffix else "Files without an extension"
        raise UnsupportedFileType(f"{kind} cannot be uploaded. Use one of: {accepted}.")
    if len(item.data) > policy.max_file_bytes:
        raise FileTooLarge(f"'{name}' is larger than the {megabytes(policy.max_file_bytes)} limit.")
    return name


def _entry(storage: WorkspaceStorage, path: Path, info: os.stat_result) -> FileEntry:
    return FileEntry(
        path=storage.relative_path(path),
        size=info.st_size,
        modified_at=datetime.fromtimestamp(info.st_mtime, timezone.utc),
        type=file_type(path.name),
    )

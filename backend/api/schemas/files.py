"""Contracts of the Files page: the signed-in user's workspace files."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    """One file. ``path`` is relative to the user's workspace, ``/``-separated."""

    model_config = ConfigDict(from_attributes=True)

    path: str
    size: int
    modified_at: datetime
    #: Lower-case extension without the dot, e.g. "pdf"; empty without one.
    type: str


class FileListOut(BaseModel):
    """Response of GET /api/files: the files, newest first, and the limits."""

    model_config = ConfigDict(from_attributes=True)

    files: list[FileOut]
    #: The sum of the files' sizes, which is what the quota counts.
    used_bytes: int
    quota_bytes: int
    #: The largest file an upload may hold.
    max_file_bytes: int
    #: What an upload may be, lower-case with the dot, e.g. ".pdf".
    allowed_extensions: list[str]

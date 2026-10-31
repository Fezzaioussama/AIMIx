"""The free space every write that grows stored data must leave on the disk that
every account's files and the SQLite database share (WORKSPACE_MIN_FREE_BYTES).

Files check it as they are written (``storage.WorkspaceStorage``); runs before
they are saved or resumed (``run_policy``); pipelines before they are saved
(``deps.disk_room``). Past the reserve the server refuses with 507 instead of
the database running out of room.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from api.exceptions import ServerStorageFull
from config.settings import Settings

#: The reserve is at most this share of the disk, so a small volume is not refused
#: from the start: 500 MB of a 1 GB volume would leave half of it unusable.
MAX_RESERVED_SHARE = 10


@dataclass(frozen=True)
class DiskReserve:
    """Keep ``min_free_bytes`` free on the disk holding ``path``, or a tenth of the
    disk when that is less; 0 is no check."""

    path: Path
    min_free_bytes: int

    def ensure_room(self, extra_bytes: int = 0) -> None:
        """Refuse a write of ``extra_bytes`` more that would cross the reserve."""
        if not self.min_free_bytes:
            return
        total, free = _total_and_free(self.path)
        if free - extra_bytes < min(self.min_free_bytes, total // MAX_RESERVED_SHARE):
            raise ServerStorageFull("The server is low on storage space. Try again later.")


def disk_reserve(settings: Settings) -> DiskReserve:
    """The reserve on the volume of AGENT_WORKSPACE_DIR, which holds the database too."""
    return DiskReserve(settings.workspace_dir, settings.workspace_min_free_bytes)


def _total_and_free(path: Path) -> tuple[int, int]:
    """The size and free space of the disk of ``path``, or of its nearest existing
    parent (a workspace directory is made on its first write)."""
    existing = next(candidate for candidate in (path, *path.parents) if candidate.exists())
    usage = shutil.disk_usage(existing)
    return usage.total, usage.free

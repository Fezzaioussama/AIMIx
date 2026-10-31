"""The confinement, overwrite and quota rules every workspace write goes through,
and how uploaded file names are made safe."""

from __future__ import annotations

import os
import stat
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.exceptions import (
    FileAlreadyExists,
    NotFound,
    ServerStorageFull,
    StorageQuotaExceeded,
    ValidationFailed,
)
from api.services.files.names import BINARY, file_type, media_type, safe_filename
from api.services.files.storage import (
    NAME_MAX_BYTES,
    WorkspaceStorage,
    WorkspaceUsage,
    user_workspace_dir,
)

MAX_FILES = 5


@pytest.fixture
def storage(tmp_path: Path) -> WorkspaceStorage:
    return WorkspaceStorage(tmp_path / "user-1", max_total_bytes=1_000, max_files=MAX_FILES)


def names(storage: WorkspaceStorage) -> list[str]:
    return sorted(storage.relative_path(path) for path, _ in storage.files())


def test_every_account_has_its_own_directory(tmp_path: Path) -> None:
    assert user_workspace_dir(tmp_path, 7) == tmp_path / "user-7"
    assert user_workspace_dir(tmp_path, 7) != user_workspace_dir(tmp_path, 8)


def test_prepare_makes_a_directory_only_the_server_can_read(storage: WorkspaceStorage) -> None:
    storage.prepare()
    assert stat.S_IMODE(storage.root.stat().st_mode) == 0o700


def test_a_new_file_never_replaces_one_unless_asked(storage: WorkspaceStorage) -> None:
    storage.save("notes.txt", b"first")

    with pytest.raises(FileAlreadyExists, match="already exists"):
        storage.save("notes.txt", b"second")
    assert (storage.root / "notes.txt").read_bytes() == b"first"

    storage.save("notes.txt", b"second", replace=True)
    assert (storage.root / "notes.txt").read_bytes() == b"second"
    # The staged copy used for the swap is gone.
    assert [path.name for path in storage.root.iterdir()] == ["notes.txt"]


def test_a_folder_is_never_replaced(storage: WorkspaceStorage) -> None:
    storage.save("reports/q3.md", b"report")
    # Not a name conflict that "replace" could settle.
    with pytest.raises(ValidationFailed, match="is a folder"):
        storage.save("reports", b"x", replace=True)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.txt",
        "reports/../../escape.txt",
        ".env",
        "notes/.git/config",
        "/etc/passwd",
        "bad\x00name.txt",
        "lone\udc80surrogate.txt",
        "x" * (NAME_MAX_BYTES + 1),
        "/".join(["x" * 200] * 30),
    ],
)
def test_paths_that_leave_the_workspace_or_hide_are_refused(
    storage: WorkspaceStorage, path: str
) -> None:
    with pytest.raises(ValidationFailed):
        storage.save(path, b"x")
    with pytest.raises(ValidationFailed):
        storage.existing(path)
    assert not (storage.root.parent / "escape.txt").exists()


def test_links_are_neither_listed_nor_followed(storage: WorkspaceStorage, tmp_path: Path) -> None:
    storage.save("real.txt", b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    (storage.root / "secret.txt").symlink_to(outside / "secret.txt")
    (storage.root / "alias.txt").symlink_to(storage.root / "real.txt")
    (storage.root / "elsewhere").symlink_to(outside, target_is_directory=True)

    assert names(storage) == ["real.txt"]
    with pytest.raises(ValidationFailed, match="outside the workspace"):
        storage.existing("secret.txt")
    with pytest.raises(ValidationFailed, match="Links are not followed"):
        storage.existing("alias.txt")
    with pytest.raises(ValidationFailed, match="outside the workspace"):
        storage.save("elsewhere/new.txt", b"x")
    assert sorted(path.name for path in outside.iterdir()) == ["secret.txt"]


def test_hidden_files_and_folders_are_not_listed(storage: WorkspaceStorage) -> None:
    storage.save("visible.md", b"x")
    (storage.root / ".hidden.txt").write_text("x")
    (storage.root / ".cache").mkdir()
    (storage.root / ".cache" / "inside.txt").write_text("x")

    assert names(storage) == ["visible.md"]


def test_the_quota_counts_every_visible_file(storage: WorkspaceStorage) -> None:
    storage.save("a.txt", b"x" * 600)

    with pytest.raises(StorageQuotaExceeded, match=r"0\.001 MB storage limit"):
        storage.save("b.txt", b"x" * 401)
    assert names(storage) == ["a.txt"]

    storage.save("b.txt", b"x" * 400)
    assert storage.usage() == WorkspaceUsage(bytes=1_000, entries=2)


def test_replacing_a_file_counts_only_the_difference(storage: WorkspaceStorage) -> None:
    storage.save("a.txt", b"x" * 900)

    storage.save("a.txt", b"y" * 1_000, replace=True)
    with pytest.raises(StorageQuotaExceeded):
        storage.save("a.txt", b"z" * 1_001, replace=True)
    assert (storage.root / "a.txt").read_bytes() == b"y" * 1_000


def test_of_two_writes_that_fit_alone_the_later_to_finish_removes_itself(
    storage: WorkspaceStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = storage.usage

    def usage() -> WorkspaceUsage:
        # Another request's file lands while this one is being written.
        (storage.root / "other.txt").write_bytes(b"x" * 600)
        return real()

    monkeypatch.setattr(storage, "usage", usage)

    with pytest.raises(StorageQuotaExceeded):
        storage.save("late.txt", b"y" * 600)
    assert names(storage) == ["other.txt"]


def test_each_save_walks_the_workspace_once(
    storage: WorkspaceStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = storage.usage
    walks: list[WorkspaceUsage] = []

    def usage() -> WorkspaceUsage:
        walks.append(real())
        return walks[-1]

    monkeypatch.setattr(storage, "usage", usage)

    storage.save("new.txt", b"x")
    storage.save("new.txt", b"xy", replace=True)

    assert walks == [WorkspaceUsage(1, 1), WorkspaceUsage(1, 1)]


def test_files_and_folders_count_against_their_own_limit(storage: WorkspaceStorage) -> None:
    for number in range(MAX_FILES - 2):
        storage.save(f"file-{number}.txt", b"")  # empty files cost no bytes
    storage.save("reports/q3.md", b"")  # a file and its folder: entries four and five

    with pytest.raises(StorageQuotaExceeded, match="more than 5 files and folders"):
        storage.save("another.txt", b"")
    with pytest.raises(StorageQuotaExceeded):
        storage.save("deep/er/still.txt", b"")
    # A refused file leaves no folder behind, and replacing adds nothing.
    assert storage.usage().entries == MAX_FILES
    assert not (storage.root / "deep").exists()
    storage.save("file-0.txt", b"new", replace=True)
    assert (storage.root / "file-0.txt").read_bytes() == b"new"


def test_a_staged_replacement_counts_and_a_stale_one_is_swept(storage: WorkspaceStorage) -> None:
    storage.prepare()
    stale = storage.root / f".upload-{'a' * 32}.part"
    stale.write_bytes(b"x" * 900)
    hour_ago = time.time() - 3_700
    os.utime(stale, (hour_ago, hour_ago))
    live = storage.root / f".upload-{'b' * 32}.part"
    live.write_bytes(b"x" * 600)

    # The live one (a replacement still being written) counts; the stale one goes.
    with pytest.raises(StorageQuotaExceeded):
        storage.save("a.txt", b"x" * 401)
    assert not stale.exists()
    assert live.exists()
    assert names(storage) == []


@pytest.mark.parametrize(
    "path",
    [
        "fake\nsecond-line.txt",
        "colour\x1b[31m.txt",
        "next\x85line.txt",
        "line\N{LINE SEPARATOR}separator.txt",
        "invoice\N{RIGHT-TO-LEFT OVERRIDE}txt.exe",
        'say "hi".txt',
        "notes: q3.md",
        "folder\r/inside.txt",
    ],
)
def test_a_new_name_with_unsafe_characters_is_refused(storage: WorkspaceStorage, path: str) -> None:
    with pytest.raises(ValidationFailed, match="cannot contain control characters"):
        storage.save(path, b"x")
    assert names(storage) == []


def test_a_file_already_named_unsafely_can_still_be_read_and_deleted(
    storage: WorkspaceStorage,
) -> None:
    storage.prepare()
    (storage.root / "old\nname.txt").write_bytes(b"x")

    assert storage.existing("old\nname.txt") == storage.root / "old\nname.txt"
    storage.delete("old\nname.txt")
    assert names(storage) == []


def test_delete_removes_the_file_and_the_folders_it_emptied(storage: WorkspaceStorage) -> None:
    storage.save("reports/q3/summary.md", b"x")
    storage.save("reports/keep.md", b"x")

    storage.delete("reports/q3/summary.md")

    assert names(storage) == ["reports/keep.md"]
    assert not (storage.root / "reports" / "q3").exists()
    with pytest.raises(NotFound, match="does not exist"):
        storage.delete("reports/q3/summary.md")


def test_a_folder_is_not_a_file(storage: WorkspaceStorage) -> None:
    storage.save("reports/q3.md", b"x")
    with pytest.raises(NotFound):
        storage.existing("reports")
    assert storage.existing("reports", directory=True) == storage.root / "reports"


# --- upload names and media types ---------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("C:\\Users\\me\\Q3 report?.PDF", "Q3 report_.pdf"),
        ("../../etc/passwd.txt", "passwd.txt"),
        (".env.md", "env.md"),
        ("  notes  .txt ", "notes.txt"),
        ("bad\x00\x07name.csv", "bad_name.csv"),
        ('a<b>c:"d"|e*.json', "a_b_c_d_e_.json"),
        ("invoice\N{RIGHT-TO-LEFT OVERRIDE}gpj.exe", "invoice_gpj.exe"),
        ("two\N{LINE SEPARATOR}lines.md", "two_lines.md"),
        (unicodedata.normalize("NFD", "Résumé.docx"), "Résumé.docx"),
        ("Отчёт за год.pdf", "Отчёт за год.pdf"),
    ],
)
def test_upload_names_are_made_safe(raw: str, expected: str) -> None:
    assert safe_filename(raw) == expected


def test_a_long_name_is_cut_but_keeps_its_extension() -> None:
    name = safe_filename("é" * 300 + ".pdf")
    assert name.endswith("é.pdf")
    assert len(name.encode("utf-8")) <= NAME_MAX_BYTES


@pytest.mark.parametrize("raw", ["", "...", " . ", "/"])
def test_a_name_with_nothing_left_is_refused(raw: str) -> None:
    with pytest.raises(ValidationFailed, match="needs a name"):
        safe_filename(raw)


def test_media_types_are_fixed_per_extension() -> None:
    assert media_type("Report.PDF") == "application/pdf"
    assert media_type("page.html") == "text/html"
    assert media_type("images/hero.JPG") == "image/jpeg"
    # An SVG can carry script: it stays a plain download.
    assert media_type("logo.svg") == BINARY
    assert media_type("tool.exe") == BINARY
    assert (file_type("a/b/Report.PDF"), file_type("README")) == ("pdf", "")


def test_remove_deletes_the_directory_and_never_follows_a_link(
    storage: WorkspaceStorage, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("not the user's")
    storage.save("a/b.txt", b"x")
    (storage.root / "link").symlink_to(outside)

    storage.remove()
    storage.remove()  # nothing left: still fine

    assert not storage.root.exists()
    assert outside.read_text() == "not the user's"


def test_a_write_that_would_leave_the_disk_too_full_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every account's files and the database share one disk: past the reserve,
    a write is refused before the database runs out of room."""
    reserve = 1_000_000
    disk = SimpleNamespace(total=10**12, used=0, free=reserve + 100)
    monkeypatch.setattr("api.services.files.disk.shutil.disk_usage", lambda _path: disk)
    shared = WorkspaceStorage(tmp_path / "user-2", 10_000, MAX_FILES, min_free_bytes=reserve)
    shared.save("fits.txt", b"x" * 50)
    disk.free = reserve - 1

    with pytest.raises(ServerStorageFull):
        shared.save("too-much.txt", b"x" * 50)
    with pytest.raises(ServerStorageFull):
        shared.save("fits.txt", b"x" * 60, replace=True)

    assert names(shared) == ["fits.txt"]
    assert (shared.root / "fits.txt").read_bytes() == b"x" * 50

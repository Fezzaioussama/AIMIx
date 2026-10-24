"""The confinement, overwrite and quota rules every workspace write goes through,
and how uploaded file names are made safe."""

from __future__ import annotations

import stat
import unicodedata
from pathlib import Path

import pytest

from api.exceptions import FileAlreadyExists, NotFound, StorageQuotaExceeded, ValidationFailed
from api.services.files.names import BINARY, file_type, media_type, safe_filename
from api.services.files.storage import NAME_MAX_BYTES, WorkspaceStorage, user_workspace_dir


@pytest.fixture
def storage(tmp_path: Path) -> WorkspaceStorage:
    return WorkspaceStorage(tmp_path / "user-1", max_total_bytes=1_000)


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
    with pytest.raises(FileAlreadyExists, match="folder"):
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
    assert storage.used_bytes() == 1_000


def test_replacing_a_file_counts_only_the_difference(storage: WorkspaceStorage) -> None:
    storage.save("a.txt", b"x" * 900)

    storage.save("a.txt", b"y" * 1_000, replace=True)
    with pytest.raises(StorageQuotaExceeded):
        storage.save("a.txt", b"z" * 1_001, replace=True)
    assert (storage.root / "a.txt").read_bytes() == b"y" * 1_000


def test_a_write_that_ends_over_the_quota_removes_itself(
    storage: WorkspaceStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage.save("other.txt", b"x" * 800)
    real = storage.used_bytes
    checks: list[int] = []

    def used_bytes() -> int:
        # The first check runs as if "other.txt" were still being written elsewhere.
        checks.append(0 if not checks else real())
        return checks[-1]

    monkeypatch.setattr(storage, "used_bytes", used_bytes)

    with pytest.raises(StorageQuotaExceeded):
        storage.save("late.txt", b"y" * 300)
    assert checks == [0, 1_100]
    assert names(storage) == ["other.txt"]


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
    assert media_type("tool.exe") == BINARY
    assert (file_type("a/b/Report.PDF"), file_type("README")) == ("pdf", "")

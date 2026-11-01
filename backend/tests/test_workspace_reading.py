"""read_workspace_file on the files agents read most: scanned PDFs (through the OCR
engine the process built) and files longer than one call shows, read on with
start_page. The tool is built through the registry, as agents get it."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path

from langchain_core.tools import BaseTool
from PIL import Image

from api.services.documents.extraction import extract_document, extraction_limits
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.registry import toolbox_tools
from config.settings import Settings
from tests.conftest import TEST_SETTINGS
from tests.test_document_scans import FakeOcr, scanned_pdf
from tests.test_documents import make_docx, make_pdf

#: Small enough that a few short pages fill one call.
OUTPUT_CHARS = 120


def reader(root: Path, ocr: FakeOcr | None = None, settings: Settings = TEST_SETTINGS) -> BaseTool:
    """read_workspace_file over ``root``, showing at most OUTPUT_CHARS per call."""
    config = replace(
        toolbox_config(settings, root),
        enabled=("read_workspace_file",),
        workspace_max_output_chars=OUTPUT_CHARS,
        ocr=ocr,
    )
    (tool,) = toolbox_tools(config)
    return tool


class HeldOcr(FakeOcr):
    """Reads like FakeOcr, but only once ``go`` is set; ``started`` says it is reading."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.go = threading.Event()

    def read(self, image: Image.Image) -> str:
        self.started.set()
        self.go.wait(timeout=10)
        return super().read(image)


def read(tool: BaseTool, path: str, start_page: int | None = None) -> str:
    arguments: dict[str, object] = {"path": path}
    if start_page is not None:
        arguments["start_page"] = start_page
    result = tool.invoke(arguments)
    assert isinstance(result, str)
    return result


def test_scanned_pages_are_read_by_the_ocr_engine(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf(2))
    ocr = FakeOcr()

    assert read(reader(tmp_path, ocr), "scan.pdf") == "Recognised text 1\n\nRecognised text 2"
    assert len(ocr.images) == 2


def test_without_an_engine_the_scan_says_ocr_is_not_available(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf(1))
    assert "OCR is not available" in read(reader(tmp_path), "scan.pdf")


def test_a_long_pdf_is_read_to_the_end_page_by_page(tmp_path: Path) -> None:
    pages = [f"Page {number} " + "x" * 40 for number in range(1, 6)]
    (tmp_path / "long.pdf").write_bytes(make_pdf(pages))
    tool = reader(tmp_path)

    first = read(tool, "long.pdf")
    second = read(tool, "long.pdf", start_page=3)
    last = read(tool, "long.pdf", start_page=5)

    assert first == (
        f"{pages[0]}\n\n{pages[1]}\n\n[Shown: pages 1-2 of 5. "
        "To read on, call read_workspace_file again with start_page=3.]"
    )
    assert second.startswith(f"{pages[2]}\n\n{pages[3]}\n\n[Shown: pages 3-4 of 5.")
    assert second.endswith("start_page=5.]")
    assert last == f"{pages[4]}\n\n[Shown: page 5 of 5, the end of the file.]"


def test_start_page_skips_the_pages_before_it_unread(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf(4))
    ocr = FakeOcr()

    text = read(reader(tmp_path, ocr), "scan.pdf", start_page=3)

    assert text == (
        "Recognised text 1\n\nRecognised text 2\n\n[Shown: pages 3-4 of 4, the end of the file.]"
    )
    assert len(ocr.images) == 2


def test_pages_ocr_s_page_budget_left_are_offered_to_the_next_call(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf(5))
    two_pages = TEST_SETTINGS.model_copy(update={"document_ocr_max_pages": 2})
    tool = reader(tmp_path, FakeOcr(), two_pages)

    first = read(tool, "scan.pdf")
    second = read(tool, "scan.pdf", start_page=3)

    assert first == (
        "Recognised text 1\n\nRecognised text 2\n\n[Shown: pages 1-2 of 5. "
        "To read on, call read_workspace_file again with start_page=3.]"
    )
    assert second.startswith("Recognised text 3\n\nRecognised text 4\n\n[Shown: pages 3-4")


class SlowOcr(FakeOcr):
    def read(self, image: Image.Image) -> str:
        time.sleep(0.02)
        return super().read(image)


def test_pages_ocr_s_time_budget_left_are_offered_to_the_next_call(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf(3))
    hurried = TEST_SETTINGS.model_copy(update={"document_ocr_max_seconds": 0.01})
    tool = reader(tmp_path, SlowOcr(), hurried)

    assert read(tool, "scan.pdf") == (
        "Recognised text 1\n\n[Shown: page 1 of 3. "
        "To read on, call read_workspace_file again with start_page=2.]"
    )


def test_a_page_longer_than_one_call_is_cut_and_reading_goes_on_at_the_next(
    tmp_path: Path,
) -> None:
    (tmp_path / "long.pdf").write_bytes(make_pdf(["word " * 60, "Next page"]))
    tool = reader(tmp_path)

    first = read(tool, "long.pdf")

    body, cut, note = first.split("\n\n")
    assert body.startswith("word word") and len(body) <= OUTPUT_CHARS
    assert cut == f"[Page 1 is longer than {OUTPUT_CHARS} characters: the rest of it is not shown.]"
    assert (
        note
        == "[Shown: page 1 of 2. To read on, call read_workspace_file again with start_page=2.]"
    )
    assert read(tool, "long.pdf", start_page=2) == (
        "Next page\n\n[Shown: page 2 of 2, the end of the file.]"
    )


def test_a_start_page_past_the_end_or_below_one_is_refused(tmp_path: Path) -> None:
    (tmp_path / "short.pdf").write_bytes(make_pdf(["One", "Two"]))
    (tmp_path / "notes.txt").write_text("short")
    tool = reader(tmp_path)

    assert read(tool, "short.pdf", start_page=3) == "This PDF has 2 pages: there is no page 3."
    assert read(tool, "notes.txt", start_page=2) == "This file has 1 page: there is no page 2."
    assert read(tool, "short.pdf", start_page=0) == "start_page counts from 1."


def test_a_long_text_file_is_read_in_pages_of_the_output_limit(tmp_path: Path) -> None:
    text = "".join(f"line {number:03d}\n" for number in range(30))  # 270 characters
    (tmp_path / "log.txt").write_text(text)
    tool = reader(tmp_path)

    shown = [read(tool, "log.txt", start_page=number) for number in (1, 2, 3)]

    notes = [part.rsplit("\n\n", 1)[1] for part in shown]
    assert notes == [
        "[Shown: page 1 of 3. To read on, call read_workspace_file again with start_page=2.]",
        "[Shown: page 2 of 3. To read on, call read_workspace_file again with start_page=3.]",
        "[Shown: page 3 of 3, the end of the file.]",
    ]
    assert "".join(part.rsplit("\n\n", 1)[0] for part in shown) == text


def test_a_short_file_has_no_note(tmp_path: Path) -> None:
    (tmp_path / "brief.md").write_text("Revenue grew 12%.")
    (tmp_path / "brief.pdf").write_bytes(make_pdf(["Revenue grew 12%."]))
    tool = reader(tmp_path)

    assert read(tool, "brief.md") == "Revenue grew 12%."
    assert read(tool, "brief.pdf") == "Revenue grew 12%."


def test_a_long_word_file_is_read_in_pages_too(tmp_path: Path) -> None:
    (tmp_path / "report.docx").write_bytes(make_docx())
    config = replace(
        toolbox_config(TEST_SETTINGS, tmp_path),
        enabled=("read_workspace_file",),
        workspace_max_output_chars=20,
    )
    (tool,) = toolbox_tools(config)

    first = read(tool, "report.docx")

    assert first.startswith("Quarterly report\nReg")
    assert first.endswith("To read on, call read_workspace_file again with start_page=2.]")


def test_the_tool_offers_start_page_and_says_how_to_use_it(tmp_path: Path) -> None:
    tool = reader(tmp_path)
    assert tool.args["start_page"]["default"] == 1
    assert "start_page" in tool.description


def test_an_agent_reading_a_scan_never_keeps_a_person_waiting(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf(1))
    (tmp_path / "note.pdf").write_bytes(make_pdf(["A typed note"]))
    one_each = TEST_SETTINGS.model_copy(
        update={
            "document_max_concurrent_extractions": 1,
            "document_agent_max_concurrent_reads": 1,
            "document_extraction_wait_seconds": 0.05,
        }
    )
    ocr = HeldOcr()
    tool = reader(tmp_path, ocr, one_each)
    agent = threading.Thread(target=read, args=(tool, "scan.pdf"))
    agent.start()
    try:
        assert ocr.started.wait(timeout=10)  # the agent holds its slot for the OCR
        upload = extract_document(
            "note.pdf", make_pdf(["A typed note"]), extraction_limits(one_each)
        )
        other_agent = read(reader(tmp_path, settings=one_each), "note.pdf")
    finally:
        ocr.go.set()
        agent.join()

    assert upload.text == "A typed note"  # a person's upload has slots of its own...
    # ...and agents take turns among themselves.
    assert other_agent == "The server is busy reading other documents. Try again in a moment."

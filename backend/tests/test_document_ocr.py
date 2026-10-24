"""The OCR adapter and how the app gets it: Tesseract through pytesseract, the startup
check that decides whether OCR is available, and its settings. Only the last test
runs the real binary, and it is skipped where Tesseract is not installed (CI)."""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from api import main
from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents import ocr
from api.services.documents.extraction import extract_document
from api.services.documents.ocr import OcrConfig, TesseractOcr, ocr_config, ocr_engine
from config.settings import Settings, pin_settings
from tests.conftest import TEST_SETTINGS
from tests.test_documents import LIMITS

ON = OcrConfig(enabled=True, languages="eng+fra", timeout_seconds=5.0)
LANGUAGE_LIST = 'List of available languages in "/usr/share/tessdata/" (3):\neng\nfra\nosd\n'


def text_image(text: str) -> Image.Image:
    """Large black words on white, which any OCR engine reads."""
    image = Image.new("L", (900, 160), "white")
    ImageDraw.Draw(image).text((30, 40), text, fill="black", font=ImageFont.load_default(60))
    return image


def installed(monkeypatch: pytest.MonkeyPatch, listing: str = LANGUAGE_LIST) -> None:
    """Pretend tesseract is on the PATH and lists ``listing``."""
    monkeypatch.setattr(ocr.shutil, "which", lambda name: f"/usr/bin/{name}")

    def run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        assert command == ["tesseract", "--list-langs"]
        assert options["timeout"] == ON.timeout_seconds
        return subprocess.CompletedProcess(command, 0, stdout=listing, stderr="")

    monkeypatch.setattr(ocr.subprocess, "run", run)


# --- the adapter ---------------------------------------------------------------------


def test_tesseract_gets_the_languages_and_timeout_and_its_text_is_trimmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def image_to_string(image: Image.Image, **options: object) -> str:
        calls.append(options)
        return "  Hello\n\x0c"

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", image_to_string)
    assert TesseractOcr("eng+fra", 7.5).read(text_image("Hello")) == "Hello"
    assert calls == [{"lang": "eng+fra", "timeout": 7.5}]


def test_a_tesseract_timeout_becomes_ocr_timed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def too_slow(image: Image.Image, **options: object) -> str:
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", too_slow)
    with pytest.raises(OcrTimedOut, match=r"7\.5 seconds"):
        TesseractOcr("eng", 7.5).read(text_image("Hello"))


@pytest.mark.parametrize(
    "error",
    [
        ocr.pytesseract.TesseractError(1, "Failed loading language"),
        FileNotFoundError("gone"),
        RuntimeError("something else broke"),
    ],
)
def test_a_tesseract_failure_is_unreadable_not_a_timeout(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail(image: Image.Image, **options: object) -> str:
        raise error

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", fail)
    with pytest.raises(DocumentUnreadable, match="OCR") as refusal:
        TesseractOcr("eng", 1.0).read(text_image("Hello"))
    assert not isinstance(refusal.value, OcrTimedOut)


# --- deciding at startup whether OCR is available -------------------------------------


def test_ocr_turned_off_gives_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    installed(monkeypatch)
    assert ocr_engine(OcrConfig(enabled=False, languages="eng", timeout_seconds=1.0)) is None


def test_an_installed_tesseract_with_the_languages_gives_the_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed(monkeypatch)
    assert isinstance(ocr_engine(ON), TesseractOcr)


def test_a_missing_tesseract_binary_gives_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    assert ocr_engine(ON) is None


def test_a_language_that_is_not_installed_gives_no_engine(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    installed(monkeypatch, listing="List of available languages (2):\neng\nosd\n")
    assert ocr_engine(ON) is None
    assert "languages_missing:fra" in caplog.text


def test_a_failing_language_check_gives_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr.shutil, "which", lambda name: f"/usr/bin/{name}")

    def hang(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 5.0)

    monkeypatch.setattr(ocr.subprocess, "run", hang)
    assert ocr_engine(ON) is None


def test_the_app_builds_its_ocr_engine_once_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[OcrConfig] = []
    engine = TesseractOcr("deu", 3.0)

    def build(config: OcrConfig) -> TesseractOcr:
        built.append(config)
        return engine

    monkeypatch.setattr(main, "ocr_engine", build)
    settings = {"document_ocr_languages": "deu", "document_ocr_timeout_seconds": 3.0}
    pin_settings(TEST_SETTINGS.model_copy(update=settings))
    try:
        application = main.create_app()
    finally:
        pin_settings(TEST_SETTINGS)
    assert built == [OcrConfig(enabled=False, languages="deu", timeout_seconds=3.0)]
    assert application.state.ocr is engine


# --- settings ------------------------------------------------------------------------


def test_ocr_settings_default_to_english_and_french_with_finite_limits() -> None:
    settings = Settings(_env_file=None)
    assert ocr_config(settings) == OcrConfig(True, "eng+fra", 15.0)
    assert (settings.document_ocr_max_pages, settings.document_ocr_dpi) == (30, 300)
    assert settings.document_max_image_pixels == 40_000_000
    assert settings.document_max_spreadsheet_rows == 5_000


@pytest.mark.parametrize("languages", ["eng fra", "eng+", "", "eng;rm -rf"])
def test_ocr_languages_must_be_tesseract_codes_joined_by_plus(languages: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, document_ocr_languages=languages)


# --- the real binary ---------------------------------------------------------------


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_tesseract_reads_an_image_and_a_scanned_pdf() -> None:
    engine = ocr_engine(OcrConfig(enabled=True, languages="eng", timeout_seconds=30.0))
    assert engine is not None
    assert "INVOICE 2026" in engine.read(text_image("INVOICE 2026")).upper()

    scan = BytesIO()
    text_image("TOTAL 42").save(scan, "PDF")
    result = extract_document("scan.pdf", scan.getvalue(), LIMITS, engine)
    assert "TOTAL 42" in result.text.upper()

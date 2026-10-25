"""Settings of the user's files and of the documents read into runs."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from config.fields import CommaList

#: Headroom over a document's size for the multipart framing around it.
MULTIPART_OVERHEAD_BYTES = 1_048_576


class DocumentSettings(BaseModel):
    # --- The user's files (api/services/files): Files page and agent artifacts --
    # Everything one user keeps, uploads and agent artifacts together.
    workspace_max_total_bytes: int = Field(
        100_000_000, ge=1, validation_alias="WORKSPACE_MAX_TOTAL_BYTES"
    )
    # Files and folders one user may keep, however small: each costs an inode and
    # makes every later write scan longer.
    workspace_max_files: int = Field(2_000, ge=1, validation_alias="WORKSPACE_MAX_FILES")
    # What the Files page accepts; each upload is capped at DOCUMENT_MAX_BYTES.
    workspace_upload_extensions: CommaList = Field(
        [
            ".pdf",
            ".docx",
            ".xlsx",
            ".pptx",
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".yaml",
            ".yml",
            ".html",
        ],
        validation_alias="WORKSPACE_UPLOAD_EXTENSIONS",
    )
    # TrueType fonts for PDF artifacts, so non-Latin text prints. Without them
    # PDFs use a built-in font that covers Western European text only.
    pdf_font_path: Path = Field(
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), validation_alias="PDF_FONT_PATH"
    )
    pdf_bold_font_path: Path = Field(
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        validation_alias="PDF_BOLD_FONT_PATH",
    )
    # --- Documents attached to a pipeline run (api/services/documents) --------
    # An upload is read into memory, so each of these bounds a different cost.
    document_max_bytes: int = Field(10_000_000, ge=1, validation_alias="DOCUMENT_MAX_BYTES")
    # Text kept from one document; the rest is dropped and the run is told so.
    document_max_chars: int = Field(120_000, ge=1, validation_alias="DOCUMENT_MAX_CHARS")
    document_max_pages: int = Field(300, ge=1, validation_alias="DOCUMENT_MAX_PAGES")
    # .docx, .xlsx and .pptx are zips: refuse one that would unpack to more than this.
    document_max_unpacked_bytes: int = Field(
        50_000_000, ge=1, validation_alias="DOCUMENT_MAX_UNPACKED_BYTES"
    )
    # ...and one with a part over this that may be XML (not a picture or other media):
    # parsing a part costs time and memory far beyond its unpacked size.
    document_max_xml_part_bytes: int = Field(
        10_000_000, ge=1, validation_alias="DOCUMENT_MAX_XML_PART_BYTES"
    )
    # Documents read at once in the process (uploads and agents alike); another
    # waits up to DOCUMENT_EXTRACTION_WAIT_SECONDS for a turn, then is refused.
    document_max_concurrent_extractions: int = Field(
        2, ge=1, validation_alias="DOCUMENT_MAX_CONCURRENT_EXTRACTIONS"
    )
    document_extraction_wait_seconds: float = Field(
        30.0, gt=0, validation_alias="DOCUMENT_EXTRACTION_WAIT_SECONDS"
    )
    # Refuse an image (or cap a rendered PDF page) past this size, before decoding it.
    document_max_image_pixels: int = Field(
        40_000_000, ge=1, validation_alias="DOCUMENT_MAX_IMAGE_PIXELS"
    )
    # Rows read from one .xlsx workbook, across all its sheets.
    document_max_spreadsheet_rows: int = Field(
        5_000, ge=1, validation_alias="DOCUMENT_MAX_SPREADSHEET_ROWS"
    )
    # OCR for scanned PDFs and images (Tesseract; api/services/documents/ocr.py).
    document_ocr_enabled: bool = Field(True, validation_alias="DOCUMENT_OCR_ENABLED")
    document_ocr_languages: str = Field(
        "eng+fra",
        pattern=r"^[A-Za-z0-9_]+(\+[A-Za-z0-9_]+)*$",
        validation_alias="DOCUMENT_OCR_LANGUAGES",
    )
    document_ocr_max_pages: int = Field(30, ge=1, validation_alias="DOCUMENT_OCR_MAX_PAGES")
    document_ocr_timeout_seconds: float = Field(
        15.0, gt=0, validation_alias="DOCUMENT_OCR_TIMEOUT_SECONDS"
    )
    # All the OCR of one document; later scanned pages are skipped and named.
    document_ocr_max_seconds: float = Field(
        120.0, gt=0, validation_alias="DOCUMENT_OCR_MAX_SECONDS"
    )
    document_ocr_dpi: int = Field(300, ge=72, validation_alias="DOCUMENT_OCR_DPI")

    @field_validator("workspace_upload_extensions", mode="after")
    @classmethod
    def _dotted_lowercase(cls, value: list[str]) -> list[str]:
        """``PDF`` and ``.pdf`` both mean ``.pdf``."""
        return [f".{item.lower().lstrip('.')}" for item in value]

    @property
    def max_request_bytes(self) -> int:
        """Largest request body accepted: one upload plus multipart overhead.

        DOCUMENT_MAX_BYTES caps every uploaded file, a run document or a file for
        the Files page alike, so this one number bounds both endpoints."""
        return self.document_max_bytes + MULTIPART_OVERHEAD_BYTES

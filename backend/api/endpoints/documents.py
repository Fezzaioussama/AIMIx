"""Document endpoints. Validate, call the service, shape the result — no logic
lives here (AGENTS.md §2)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, UploadFile

from api.deps import DocumentLimits, DocumentOcr
from api.schemas.documents import DocumentOut
from api.services.documents import extraction
from api.throttling import user_rate_limit

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/extract", dependencies=[Depends(user_rate_limit)])
def extract_document(file: UploadFile, limits: DocumentLimits, ocr: DocumentOcr) -> DocumentOut:
    """Read an uploaded PDF, Office file, image, HTML or text file and return its text.

    Nothing is stored: the client puts the text in a run input.
    """
    # One byte past the limit is enough for the service to see the file is too large,
    # without reading the rest of an oversized upload into memory.
    data = file.file.read(limits.max_bytes + 1)
    result = extraction.extract_document(file.filename or "", data, limits, ocr)
    return DocumentOut.model_validate(asdict(result))

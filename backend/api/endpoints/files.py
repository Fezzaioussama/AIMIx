"""File endpoints: the signed-in user's workspace, shared with their agents.
Validate, call the service, shape the result — no logic lives here (AGENTS.md §2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import FileResponse

from api.deps import FileUploads, UserFiles
from api.schemas.files import FileListOut, FileOut
from api.services.files import service as file_service

router = APIRouter(prefix="/files", tags=["files"])

#: A download is always saved, never displayed: even HTML or SVG that a user or an
#: agent stored cannot run as a page of this origin (stored XSS), and the browser
#: may not guess another type.
DOWNLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "no-store",
}


@router.get("")
def list_files(storage: UserFiles, policy: FileUploads) -> FileListOut:
    return FileListOut.model_validate(file_service.list_files(storage, policy))


@router.post("", status_code=201)
def upload_files(
    files: Annotated[list[UploadFile], File()],
    storage: UserFiles,
    policy: FileUploads,
    replace: Annotated[bool, Form()] = False,
) -> list[FileOut]:
    """Store one or more files (multipart ``files``); ``replace=true`` overwrites."""
    # One byte past the cap is enough for the service to refuse a file, without
    # reading the rest of an oversized one into memory.
    uploads = [
        file_service.Upload(item.filename or "", item.file.read(policy.max_file_bytes + 1))
        for item in files
    ]
    stored = file_service.upload(storage, uploads, policy, replace=replace)
    return [FileOut.model_validate(entry) for entry in stored]


@router.get("/{path:path}", response_class=FileResponse)
def download_file(path: str, storage: UserFiles) -> FileResponse:
    item = file_service.download(storage, path)
    return FileResponse(
        item.location,
        media_type=item.media_type,
        filename=item.filename,
        content_disposition_type="attachment",
        headers=DOWNLOAD_HEADERS,
    )


@router.delete("/{path:path}", status_code=204)
def delete_file(path: str, storage: UserFiles) -> Response:
    file_service.delete(storage, path)
    return Response(status_code=204)

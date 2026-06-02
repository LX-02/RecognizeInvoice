from __future__ import annotations

from pydantic import BaseModel


class UploadRecord(BaseModel):
    id: str
    filename: str
    stored_filename: str
    content_type: str | None
    sha256: str
    size: int
    uploaded_at: str
    has_result: bool = False


class UploadResponse(BaseModel):
    duplicate: bool
    file: UploadRecord

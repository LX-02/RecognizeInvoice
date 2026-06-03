from __future__ import annotations

from pydantic import BaseModel


class OcrModel(BaseModel):
    key: str
    label: str
    model: str


class OcrModelsResponse(BaseModel):
    default: str
    models: list[OcrModel]


class RecognitionRequest(BaseModel):
    model_key: str | None = None


class UploadRecord(BaseModel):
    id: str
    filename: str
    stored_filename: str
    content_type: str | None
    sha256: str
    size: int
    uploaded_at: str
    has_result: bool = False
    has_legacy_result: bool = False
    result_model_keys: list[str] = []


class UploadResponse(BaseModel):
    duplicate: bool
    file: UploadRecord

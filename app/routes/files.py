from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas import UploadResponse
from app.services.model_config import get_default_model_key, get_ocr_model
from app.storage import get_record, list_upload_records, load_result, save_upload

router = APIRouter()


@router.get("/api/files")
def list_files() -> list[dict[str, Any]]:
    return list_upload_records()


@router.post("/api/upload", response_model=UploadResponse)
async def upload_invoice(file: Annotated[UploadFile, File()]) -> UploadResponse:
    return save_upload(file, await file.read())


@router.get("/api/results/{file_id}")
def get_result(file_id: str, model_key: str | None = None) -> Any:
    if not model_key:
        return load_result(file_id)

    model_config = get_ocr_model(model_key)
    allow_legacy_fallback = model_config["key"] == get_default_model_key()
    return load_result(
        file_id,
        model_config["key"],
        allow_legacy_fallback=allow_legacy_fallback,
    )


@router.get("/uploads/{file_id}")
def preview_upload(file_id: str) -> FileResponse:
    record = get_record(file_id)
    path = settings.upload_dir / record["stored_filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file missing")
    return FileResponse(path, media_type=record.get("content_type"))

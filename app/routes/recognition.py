from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.ocr import recognize_file
from app.storage import get_record, save_result

router = APIRouter()


@router.post("/api/recognize/{file_id}")
def recognize_invoice(file_id: str) -> Any:
    record = get_record(file_id)
    upload_path = settings.upload_dir / record["stored_filename"]
    if not upload_path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file missing")

    saved_result = recognize_file(record, upload_path)
    save_result(file_id, saved_result)
    return saved_result

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.schemas import UploadRecord, UploadResponse

_index_lock = threading.Lock()


def ensure_dirs() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.result_dir.mkdir(parents=True, exist_ok=True)
    settings.static_dir.mkdir(parents=True, exist_ok=True)
    if not settings.index_path.exists():
        settings.index_path.write_text("[]", encoding="utf-8")


def read_index() -> list[dict[str, Any]]:
    ensure_dirs()
    try:
        return json.loads(settings.index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def write_index(records: list[dict[str, Any]]) -> None:
    ensure_dirs()
    settings.index_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def result_path(file_id: str) -> Path:
    return settings.result_dir / f"{file_id}.json"


def get_record(file_id: str) -> dict[str, Any]:
    for record in read_index():
        if record["id"] == file_id:
            record["has_result"] = result_path(file_id).exists()
            return record
    raise HTTPException(status_code=404, detail="File not found")


def list_upload_records() -> list[dict[str, Any]]:
    records = read_index()
    for record in records:
        record["has_result"] = result_path(record["id"]).exists()
    return sorted(records, key=lambda item: item["uploaded_at"], reverse=True)


def save_upload(file: UploadFile, content: bytes) -> UploadResponse:
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail="Only image or PDF files are supported")

    digest = hashlib.sha256(content).hexdigest()
    with _index_lock:
        records = read_index()
        for record in records:
            if record["sha256"] == digest:
                record["has_result"] = result_path(record["id"]).exists()
                return UploadResponse(duplicate=True, file=UploadRecord(**record))

        file_id = uuid4().hex
        stored_filename = f"{file_id}{suffix}"
        upload_path = settings.upload_dir / stored_filename
        upload_path.write_bytes(content)

        record = {
            "id": file_id,
            "filename": file.filename or stored_filename,
            "stored_filename": stored_filename,
            "content_type": file.content_type,
            "sha256": digest,
            "size": len(content),
            "uploaded_at": datetime.now(UTC).isoformat(),
            "has_result": False,
        }
        records.append(record)
        write_index(records)

    return UploadResponse(duplicate=False, file=UploadRecord(**record))


def load_result(file_id: str) -> Any:
    get_record(file_id)
    path = result_path(file_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return json.loads(path.read_text(encoding="utf-8"))


def save_result(file_id: str, payload: dict[str, Any]) -> None:
    result_path(file_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with _index_lock:
        records = read_index()
        for record in records:
            if record["id"] == file_id:
                record["has_result"] = True
                break
        write_index(records)

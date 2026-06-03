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


def legacy_result_path(file_id: str) -> Path:
    return settings.result_dir / f"{file_id}.json"


def result_path(file_id: str, model_key: str | None = None) -> Path:
    if model_key:
        return settings.result_dir / f"{file_id}_{model_key}.json"
    return legacy_result_path(file_id)


def result_model_keys(file_id: str) -> list[str]:
    ensure_dirs()
    prefix = f"{file_id}_"
    keys = []
    for path in settings.result_dir.glob(f"{prefix}*.json"):
        key = path.stem[len(prefix) :]
        if key:
            keys.append(key)
    return sorted(set(keys))


def result_paths(file_id: str) -> list[Path]:
    paths = [legacy_result_path(file_id)]
    paths.extend(result_path(file_id, key) for key in result_model_keys(file_id))
    return [path for path in paths if path.exists()]


def latest_result_path(file_id: str) -> Path | None:
    paths = result_paths(file_id)
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def result_state(file_id: str) -> dict[str, Any]:
    has_legacy_result = legacy_result_path(file_id).exists()
    model_keys = result_model_keys(file_id)
    return {
        "has_result": has_legacy_result or bool(model_keys),
        "has_legacy_result": has_legacy_result,
        "result_model_keys": model_keys,
    }


def get_record(file_id: str) -> dict[str, Any]:
    for record in read_index():
        if record["id"] == file_id:
            record.update(result_state(file_id))
            return record
    raise HTTPException(status_code=404, detail="File not found")


def list_upload_records() -> list[dict[str, Any]]:
    records = read_index()
    for record in records:
        record.update(result_state(record["id"]))
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
                record.update(result_state(record["id"]))
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
            "has_legacy_result": False,
            "result_model_keys": [],
        }
        records.append(record)
        write_index(records)

    return UploadResponse(duplicate=False, file=UploadRecord(**record))


def load_result(
    file_id: str,
    model_key: str | None = None,
    *,
    allow_legacy_fallback: bool = False,
) -> Any:
    get_record(file_id)
    path = result_path(file_id, model_key)
    if model_key and not path.exists() and allow_legacy_fallback:
        path = legacy_result_path(file_id)
    if not model_key:
        path = latest_result_path(file_id) or path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return json.loads(path.read_text(encoding="utf-8"))


def save_result(file_id: str, model_key: str, payload: dict[str, Any]) -> None:
    result_path(file_id, model_key).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with _index_lock:
        records = read_index()
        for record in records:
            if record["id"] == file_id:
                record["has_result"] = True
                record["has_legacy_result"] = legacy_result_path(file_id).exists()
                record["result_model_keys"] = result_model_keys(file_id)
                break
        write_index(records)

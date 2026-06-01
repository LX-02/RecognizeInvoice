from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
RESULT_DIR = DATA_DIR / "results"
STATIC_DIR = ROOT_DIR / "static"
INDEX_PATH = DATA_DIR / "index.json"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-vl-ocr-latest"

PROMPT = """请识别这张企业报销相关票据或发票图片，可能包括增值税发票、数电票、餐饮发票、火车票、出租车票、行程单、电子发票等。

请只输出 JSON，不要输出解释文字。无法识别的字段填 null。金额尽量输出数字字符串，日期尽量输出 YYYY-MM-DD。

字段包括：
invoice_type, invoice_code, invoice_number, digital_invoice_number, issue_date, check_code,
buyer_name, buyer_tax_id,
seller_name, seller_tax_id,
amount_without_tax, tax_rate, tax_amount, total_amount, total_amount_cn,
items,
remark, issuer,
ocr_text

items 是数组，每项包含：
name, spec, unit, quantity, unit_price, amount, tax_rate, tax_amount"""


app = FastAPI(title="RecognizeInvoice MVP")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_index_lock = threading.Lock()


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


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        INDEX_PATH.write_text("[]", encoding="utf-8")


def read_index() -> list[dict[str, Any]]:
    ensure_dirs()
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def write_index(records: list[dict[str, Any]]) -> None:
    ensure_dirs()
    INDEX_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def result_path(file_id: str) -> Path:
    return RESULT_DIR / f"{file_id}.json"


def get_record(file_id: str) -> dict[str, Any]:
    for record in read_index():
        if record["id"] == file_id:
            record["has_result"] = result_path(file_id).exists()
            return record
    raise HTTPException(status_code=404, detail="File not found")


def to_data_url(path: Path, content_type: str | None) -> str:
    mime_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def parse_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S | re.I)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def update_result_flag(file_id: str) -> None:
    with _index_lock:
        records = read_index()
        for record in records:
            if record["id"] == file_id:
                record["has_result"] = True
                break
        write_index(records)


@app.on_event("startup")
def on_startup() -> None:
    ensure_dirs()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/files")
def list_files() -> list[dict[str, Any]]:
    records = read_index()
    for record in records:
        record["has_result"] = result_path(record["id"]).exists()
    return sorted(records, key=lambda item: item["uploaded_at"], reverse=True)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_invoice(file: UploadFile = File(...)) -> UploadResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only image files are supported")

    digest = hashlib.sha256(content).hexdigest()
    with _index_lock:
        records = read_index()
        for record in records:
            if record["sha256"] == digest:
                record["has_result"] = result_path(record["id"]).exists()
                return UploadResponse(duplicate=True, file=UploadRecord(**record))

        file_id = uuid4().hex
        stored_filename = f"{file_id}{suffix}"
        upload_path = UPLOAD_DIR / stored_filename
        upload_path.write_bytes(content)

        record = {
            "id": file_id,
            "filename": file.filename or stored_filename,
            "stored_filename": stored_filename,
            "content_type": file.content_type,
            "sha256": digest,
            "size": len(content),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "has_result": False,
        }
        records.append(record)
        write_index(records)

    return UploadResponse(duplicate=False, file=UploadRecord(**record))


@app.get("/api/results/{file_id}")
def get_result(file_id: str) -> Any:
    get_record(file_id)
    path = result_path(file_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/recognize/{file_id}")
def recognize_invoice(file_id: str) -> Any:
    record = get_record(file_id)
    upload_path = UPLOAD_DIR / record["stored_filename"]
    if not upload_path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file missing")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY is not configured")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="openai package is not installed") from exc

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
    )

    try:
        completion = client.chat.completions.create(
            model=os.getenv("QWEN_OCR_MODEL", DEFAULT_MODEL),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": to_data_url(upload_path, record.get("content_type"))}},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )
        content = completion.choices[0].message.content or ""
        extracted = parse_json_object(content)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Qwen OCR request failed: {exc}") from exc

    saved_result = {
        "file": record,
        "model": os.getenv("QWEN_OCR_MODEL", DEFAULT_MODEL),
        "recognized_at": datetime.now(timezone.utc).isoformat(),
        "result": extracted,
    }
    result_path(file_id).write_text(json.dumps(saved_result, ensure_ascii=False, indent=2), encoding="utf-8")
    update_result_flag(file_id)
    return saved_result


@app.get("/uploads/{file_id}")
def preview_upload(file_id: str) -> FileResponse:
    record = get_record(file_id)
    path = UPLOAD_DIR / record["stored_filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file missing")
    return FileResponse(path, media_type=record.get("content_type"))

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.schemas import OcrModelsResponse
from app.services.model_config import get_ocr_models_response

router = APIRouter()


@router.get("/api/models", response_model=OcrModelsResponse)
def list_models() -> dict[str, Any]:
    return get_ocr_models_response()

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from app.config import settings

MODEL_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def _config_error(message: str) -> HTTPException:
    return HTTPException(status_code=500, detail=f"OCR model config error: {message}")


def load_ocr_model_config() -> dict[str, Any]:
    path = settings.ocr_model_config_path
    if not path.exists():
        raise _config_error(f"{path} does not exist")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _config_error(f"{path} is not valid JSON") from exc

    raw_models = payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise _config_error("models must be a non-empty list")

    models: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for index, raw_model in enumerate(raw_models, start=1):
        if not isinstance(raw_model, dict):
            raise _config_error(f"models[{index}] must be an object")

        key = str(raw_model.get("key") or "").strip()
        label = str(raw_model.get("label") or key).strip()
        model = str(raw_model.get("model") or "").strip()
        if not key:
            raise _config_error(f"models[{index}].key is required")
        if not MODEL_KEY_PATTERN.fullmatch(key):
            raise _config_error(
                f"models[{index}].key only supports letters, numbers, dots, "
                "underscores, and hyphens"
            )
        if key in seen_keys:
            raise _config_error(f"duplicate model key: {key}")
        if not model:
            raise _config_error(f"models[{index}].model is required")

        seen_keys.add(key)
        models.append({"key": key, "label": label or key, "model": model})

    default_key = str(payload.get("default") or models[0]["key"]).strip()
    if default_key not in seen_keys:
        raise _config_error("default must match one model key")

    return {"default": default_key, "models": models}


def get_ocr_models_response() -> dict[str, Any]:
    return load_ocr_model_config()


def get_ocr_model(model_key: str | None = None) -> dict[str, str]:
    config = load_ocr_model_config()
    selected_key = model_key or config["default"]
    for model in config["models"]:
        if model["key"] == selected_key:
            return model
    raise HTTPException(status_code=400, detail=f"Unknown OCR model: {selected_key}")


def get_default_model_key() -> str:
    return str(load_ocr_model_config()["default"])

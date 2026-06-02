from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    upload_dir: Path = ROOT_DIR / "data" / "uploads"
    result_dir: Path = ROOT_DIR / "data" / "results"
    static_dir: Path = ROOT_DIR / "static"
    index_path: Path = ROOT_DIR / "data" / "index.json"
    allowed_extensions: frozenset[str] = frozenset(
        {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".pdf"}
    )
    default_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_model: str = "qwen-vl-ocr-latest"


settings = Settings()

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.files import router as files_router
from app.routes.models import router as models_router
from app.routes.recognition import router as recognition_router
from app.storage import ensure_dirs


def configure_logging() -> None:
    log_level_name = os.getenv("LOG_LEVEL", "DEBUG").upper()
    app_log_level = getattr(logging, log_level_name, logging.DEBUG)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    logging.getLogger("app").setLevel(app_log_level)

    for logger_name in ("asyncio", "watchfiles", "uvicorn"):
        logging.getLogger(logger_name).setLevel(logging.INFO)

    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_dirs()
    yield


app = FastAPI(title="RecognizeInvoice MVP", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
app.include_router(files_router)
app.include_router(models_router)
app.include_router(recognition_router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info").lower(),
    )

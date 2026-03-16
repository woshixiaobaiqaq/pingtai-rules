from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "templates" / "index.html"

web_router = APIRouter()


@web_router.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


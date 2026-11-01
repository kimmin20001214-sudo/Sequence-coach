"""배포용 진입점: /api 아래에 API를, 그 외 경로에는 프론트 빌드 결과(dist)를 제공한다."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .main import app as api_app

DIST = Path(os.environ.get("FRONTEND_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist")

server = FastAPI(title="Sequence Coach")
server.mount("/api", api_app)
if DIST.is_dir():
    server.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")

"""배포용 진입점: /api 아래에 API를, 그 외 경로에는 프론트 빌드 결과(dist)를 제공한다."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import auth
from .main import app as api_app

DIST = Path(os.environ.get("FRONTEND_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist")

server = FastAPI(title="Sequence Coach")
# 하위 앱(/api)의 시작 훅은 mount하면 실행되지 않아서 여기서 직접 등록한다.
server.router.on_startup.append(auth.seed_accounts)
server.mount("/api", api_app)
if DIST.is_dir():
    server.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")

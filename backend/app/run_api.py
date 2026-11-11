"""홈페이지가 쓰는 실행 API: 작업을 만들고 Copilot Studio 에이전트를 호출한다(방향 A)."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db, preflight
from .agent_api import status_of
from .agents import orchestrator, runner

router = APIRouter(tags=["run"])
BUSY_SECONDS = 300


def _is_busy(job: dict | None) -> bool:
    if not job or job["state"] != "ANALYZING":
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["updated_at"])).total_seconds()
    return age < BUSY_SECONDS


@router.get("/agent-mode")
def agent_mode():
    """화면이 에이전트 연결 상태를 알려 주기 위한 값. directline | demo | null"""
    return {"mode": runner.mode()}


class Answer(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=500)


class RunRequest(BaseModel):
    answers: list[Answer] = Field(default=[], max_length=50)


@router.post("/projects/{project_id}/run", status_code=202)
def run(project_id: str, body: RunRequest | None = None):
    """분석을 시작해요. 이전 질문에 답했다면 answers에 담아 다시 분석해요."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
    problems = preflight.check(project)
    if problems:
        raise HTTPException(422, problems)
    if not runner.mode():
        raise HTTPException(503, "에이전트가 아직 연결되지 않았어요. 관리자에게 Copilot Studio 연결을 요청해 주세요.")
    if _is_busy(db.latest_job(project_id)):
        raise HTTPException(409, "이미 분석 중이에요. 잠시 후 다시 시도해 주세요.")
    answers = [a.model_dump() for a in body.answers] if body else None
    job, _ = orchestrator.start_job(project_id, answers=answers)
    runner.launch(job["id"])
    return status_of(db.get_job(job["id"]))

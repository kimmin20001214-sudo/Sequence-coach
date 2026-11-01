"""Copilot Studio 에이전트가 도구(REST API tool)로 부르는 API.

모든 /agent/* 경로는 X-API-Key 헤더가 필요하다. 서버 환경변수 AGENT_API_KEY가 없으면 닫혀 있다.
"""
import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from . import db
from .agents import orchestrator
from .agents.schemas import LlmAnalysis


def require_key(x_api_key: str = Header(default="", description="서버에 설정된 AGENT_API_KEY")):
    key = os.environ.get("AGENT_API_KEY")
    if not key:
        raise HTTPException(503, "AGENT_API_KEY가 설정되지 않아 에이전트 API가 닫혀 있어요.")
    if not hmac.compare_digest(x_api_key.encode(), key.encode()):
        raise HTTPException(401, "API 키가 올바르지 않아요.")


router = APIRouter(prefix="/agent", tags=["agent-tools"], dependencies=[Depends(require_key)])


class Verification(BaseModel):
    passed: bool


def status_of(job: dict) -> dict:
    events = db.list_events(job["id"])
    questions = next((e["data"].get("questions", []) for e in reversed(events) if e["kind"] == "questions"), [])
    return {"project_id": job["project_id"], "job_id": job["id"], "state": job["state"],
            "iteration": job["iteration"], "max_iter": job["max_iter"], "updated_at": job["updated_at"],
            "events": events, "questions": questions}


def project_status(project_id: str) -> dict:
    job = db.latest_job(project_id)
    if not job:
        if not db.get_project(project_id):
            raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
        return {"project_id": project_id, "job_id": None, "state": "INPUT_VALIDATED", "iteration": 0,
                "max_iter": 5, "events": [], "questions": []}
    return status_of(job)


def _run(fn, *args):
    try:
        return fn(*args)
    except KeyError:
        raise HTTPException(404, "대상을 찾을 수 없어요.")
    except orchestrator.InvalidTransition as e:
        raise HTTPException(409, str(e))


@router.post("/projects/{project_id}/jobs", operation_id="startJob", status_code=201,
             summary="작업 시작 (분석 단계로 이동)")
def start_job(project_id: str):
    """직접 시작 방식(B 단독)용. 새 작업을 만들고 ANALYZING 상태로 넘겨요. 홈페이지 실행 버튼(A)으로 시작한 작업은 getJob을 쓰세요."""
    job, project = _run(orchestrator.start_job, project_id)
    return {"job": status_of(job), "project": project}


@router.get("/projects/{project_id}/status", operation_id="getStatus", summary="현재 상태 조회")
def get_status(project_id: str):
    """가장 최근 작업의 상태, 단계별 기록, 사용자에게 물어볼 질문 목록을 돌려줘요."""
    return project_status(project_id)


@router.get("/jobs/{job_id}", operation_id="getJob", summary="작업과 분석할 입력 조회")
def get_job(job_id: str):
    """백엔드가 시작한 작업(job_id)의 상태와 분석할 입력(plc_config, io_list, conditions)을 돌려줘요."""
    job, project = _run(orchestrator.get_job_input, job_id)
    return {"job": status_of(job), "project": project}


@router.post("/jobs/{job_id}/requirements", operation_id="submitRequirements",
             summary="분석 결과 제출")
def submit_requirements(job_id: str, analysis: LlmAnalysis):
    """분석 에이전트가 구조화한 조건을 보내요. I/O 목록에 없는 신호가 있으면 질문이 생기고(NEEDS_INPUT),
    없으면 DESIGNING으로 넘어가요. 비상정지 조건은 필요하면 자동으로 추가돼요."""
    return status_of(_run(orchestrator.submit_requirements, job_id, analysis))


@router.post("/jobs/{job_id}/verification", operation_id="reportVerification",
             summary="검증 결과 보고")
def report_verification(job_id: str, result: Verification):
    """검증 에이전트가 통과 여부를 보고해요. 실패가 반복돼 최대 횟수를 넘으면 ESCALATED가 돼요."""
    return status_of(_run(orchestrator.report_verification, job_id, result.passed))


def build_openapi(base_url: str | None = None) -> dict:
    """Copilot Studio에 가져올 수 있도록 /agent 경로만 담은 OpenAPI 3.0 문서."""
    spec = get_openapi(
        title="MELSEC PLC 설계 지원 - 에이전트 도구", version="1.0.0", openapi_version="3.0.3",
        description="Copilot Studio 에이전트가 호출하는 상태 관리·검증 API", routes=router.routes,
    )
    spec["components"]["securitySchemes"] = {"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
    spec["security"] = [{"apiKey": []}]
    if base_url:
        spec["servers"] = [{"url": base_url.rstrip("/")}]
    for path in spec["paths"].values():
        for op in path.values():
            op["parameters"] = [p for p in op.get("parameters", []) if p["name"].lower() != "x-api-key"]
    return spec

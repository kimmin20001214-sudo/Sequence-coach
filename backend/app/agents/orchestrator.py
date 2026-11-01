"""팀장: 전체 단계를 상태 머신으로 관리하고 결과를 jobs/job_events에 기록한다.

AI 판단(분석·설계·검증·수정)은 Copilot Studio 에이전트가 하고, 이 모듈은 에이전트가 API로 보낸
결과를 받아 규칙대로 상태를 넘긴다. DESIGNING 이후는 다음 이슈에서 채울 자리(stub)다.
"""
from .. import db
from ..schemas import ProjectInput
from .analyzer import finalize
from .schemas import LlmAnalysis

TRANSITIONS: dict[str, set[str]] = {
    "INPUT_VALIDATED": {"ANALYZING"},
    "ANALYZING": {"DESIGNING", "NEEDS_INPUT", "FAILED"},
    "NEEDS_INPUT": set(),
    "DESIGNING": {"VERIFYING", "FAILED"},
    "VERIFYING": {"COMPLETED", "FIXING", "ESCALATED"},
    "FIXING": {"VERIFYING"},
    "COMPLETED": {"GENERATING"},
    "GENERATING": {"DELIVERED", "FAILED"},
    "DELIVERED": set(),
    "ESCALATED": set(),
    "FAILED": set(),
}


class InvalidTransition(RuntimeError):
    pass


def _move(job: dict, to: str, kind: str, data: dict | None = None, iteration: int | None = None) -> dict:
    if to not in TRANSITIONS[job["state"]]:
        raise InvalidTransition(f"{job['state']} 상태에서는 {to}(으)로 넘어갈 수 없어요.")
    db.update_job(job["id"], to, iteration)
    db.add_event(job["id"], to, kind, data or {})
    db.update_project_status(job["project_id"], to)
    return db.get_job(job["id"])


def start_job(project_id: str, max_iter: int = 5) -> tuple[dict, dict]:
    """작업을 만들고 ANALYZING으로 넘긴다. 분석 에이전트가 읽을 프로젝트 입력도 함께 돌려준다."""
    stored = db.get_project(project_id)
    if not stored:
        raise KeyError(project_id)
    job = db.create_job(project_id, "INPUT_VALIDATED", max_iter)
    db.add_event(job["id"], "INPUT_VALIDATED", "created", {})
    job = _move(job, "ANALYZING", "started")
    return job, stored


def submit_requirements(job_id: str, analysis: LlmAnalysis) -> dict:
    """분석 에이전트의 결과를 점검·보완한다. 질문이 있으면 NEEDS_INPUT, 없으면 DESIGNING."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "ANALYZING":
        raise InvalidTransition(f"{job['state']} 상태에서는 분석 결과를 받을 수 없어요.")
    project = ProjectInput.model_validate(db.get_project(job["project_id"]))
    req = finalize(project, analysis)
    if req.questions:
        return _move(job, "NEEDS_INPUT", "questions", req.model_dump())
    return _move(job, "DESIGNING", "requirements", req.model_dump())


def report_verification(job_id: str, passed: bool) -> dict:
    """검증 결과를 받아 다음 상태를 정한다. 수정 횟수가 max_iter에 도달하면 ESCALATED."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if passed:
        return _move(job, "COMPLETED", "verified")
    if job["iteration"] >= job["max_iter"]:
        return _move(job, "ESCALATED", "escalated", {"max_iter": job["max_iter"]})
    return _move(job, "FIXING", "fix_requested", {"iteration": job["iteration"] + 1}, job["iteration"] + 1)

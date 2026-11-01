"""팀장 에이전트: 전체 단계를 상태 머신으로 움직이고 결과를 jobs/job_events에 기록한다.

DESIGNING 이후(설계·검증·수정·파일 생성)는 다음 이슈에서 채울 자리(stub)다.
"""
from .. import db
from ..schemas import ProjectInput
from .analyzer import analyze

TRANSITIONS: dict[str, set[str]] = {
    "INPUT_VALIDATED": {"ANALYZING"},
    "ANALYZING": {"DESIGNING", "NEEDS_INPUT", "FAILED"},
    "NEEDS_INPUT": {"ANALYZING"},
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
        raise InvalidTransition(f"{job['state']} → {to} 로는 넘어갈 수 없어요.")
    db.update_job(job["id"], to, iteration)
    db.add_event(job["id"], to, kind, data or {})
    db.update_project_status(job["project_id"], to)
    return db.get_job(job["id"])


def start_analysis(project_id: str, max_iter: int = 5) -> dict:
    """프로젝트 입력을 분석하고, 질문이 없으면 DESIGNING으로 넘긴다."""
    stored = db.get_project(project_id)
    if not stored:
        raise KeyError(project_id)
    project = ProjectInput.model_validate(stored)

    job = db.create_job(project_id, "INPUT_VALIDATED", max_iter)
    db.add_event(job["id"], "INPUT_VALIDATED", "created", {})
    job = _move(job, "ANALYZING", "started")
    try:
        req = analyze(project)
    except Exception as e:
        _move(job, "FAILED", "error", {"message": str(e)})
        raise
    if req.questions:
        return _move(job, "NEEDS_INPUT", "questions", req.model_dump())
    return _move(job, "DESIGNING", "requirements", req.model_dump())


def report_verification(job_id: str, passed: bool) -> dict:
    """검증 결과를 받아 다음 상태를 정한다. 수정 횟수가 max_iter에 도달하면 ESCALATED."""
    job = db.get_job(job_id)
    if passed:
        return _move(job, "COMPLETED", "verified")
    if job["iteration"] >= job["max_iter"]:
        return _move(job, "ESCALATED", "escalated", {"max_iter": job["max_iter"]})
    return _move(job, "FIXING", "fix_requested", {"iteration": job["iteration"] + 1}, job["iteration"] + 1)

"""팀장: 전체 단계를 상태 머신으로 관리하고 결과를 jobs/job_events에 기록한다.

AI 판단(분석·설계·검증·수정)은 Copilot Studio 에이전트가 하고, 이 모듈은 에이전트가 API로 보낸
결과를 받아 규칙대로 상태를 넘긴다. 설계 초안은 안전 검토가 연결되기 전까지 DESIGNING에 둔다.
"""
from .. import db
from ..contracts import JOB_TRANSITIONS as TRANSITIONS
from ..contracts import StructuredRequirements
from ..schemas import ProjectInput
from .analyzer import finalize
from .designer import create_draft
from .schemas import LlmAnalysis

ACTIVE_STATES = {"INPUT_VALIDATED", "ANALYZING", "DESIGNING", "VERIFYING", "FIXING", "COMPLETED", "GENERATING"}


class InvalidTransition(RuntimeError):
    pass


def _move(job: dict, to: str, kind: str, data: dict | None = None, iteration: int | None = None) -> dict:
    if to not in TRANSITIONS[job["state"]]:
        raise InvalidTransition(f"{job['state']} 상태에서는 {to}(으)로 넘어갈 수 없어요.")
    db.update_job(job["id"], to, iteration)
    db.add_event(job["id"], to, kind, data or {})
    db.update_project_status(job["project_id"], to)
    return db.get_job(job["id"])


def start_job(project_id: str, max_iter: int = 5, answers: list[dict] | None = None) -> tuple[dict, dict]:
    """작업을 만들고 ANALYZING으로 넘긴다. 분석 에이전트가 읽을 프로젝트 입력도 함께 돌려준다.

    answers는 이전 질문에 대한 사용자 답변([{question, answer}])이며 새 작업에 기록돼 재분석에 쓰인다."""
    stored = db.get_project(project_id)
    if not stored:
        raise KeyError(project_id)
    job = db.create_job(project_id, "INPUT_VALIDATED", max_iter)
    db.add_event(job["id"], "INPUT_VALIDATED", "created", {})
    if answers:
        db.add_event(job["id"], "INPUT_VALIDATED", "answers", {"answers": answers})
    job = _move(job, "ANALYZING", "started")
    return job, stored


def job_answers(job_id: str) -> list[dict]:
    return next((e["data"]["answers"] for e in db.list_events(job_id) if e["kind"] == "answers"), [])


def get_job_input(job_id: str) -> tuple[dict, dict]:
    """작업과 그 프로젝트 입력(plc_config, io_list, conditions, answers)을 돌려준다."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    return job, {**db.get_project(job["project_id"]), "answers": job_answers(job_id)}


def fail_job(job_id: str, reason: str) -> dict:
    """에이전트 호출 실패 등으로 더 진행할 수 없을 때 FAILED로 기록한다. 이미 끝난 작업은 그대로 둔다."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if "FAILED" not in TRANSITIONS[job["state"]]:
        return job
    return _move(job, "FAILED", "error", {"reason": reason})


def submit_requirements(job_id: str, analysis: LlmAnalysis) -> dict:
    """분석 에이전트의 결과를 점검·보완한다. 질문이 있으면 NEEDS_INPUT, 없으면 DESIGNING."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "ANALYZING":
        raise InvalidTransition(f"{job['state']} 상태에서는 분석 결과를 받을 수 없어요.")
    project = ProjectInput.model_validate(db.get_project(job["project_id"]))
    req = finalize(project, analysis, job_answers(job_id))
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


def generate_design(job_id: str) -> dict:
    """저장된 분석 결과만 사용한다. 초안은 기록하되 안전 검토를 대신하지 않는다."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "DESIGNING":
        raise InvalidTransition(f"{job['state']} 상태에서는 설계 초안을 만들 수 없어요.")
    events = db.list_events(job_id)
    existing = next((e["data"] for e in events if e["kind"] == "design"), None)
    if existing is not None:
        return {"job": job, "design": existing}
    requirements = next((e["data"] for e in reversed(events) if e["kind"] == "requirements"), None)
    try:
        if requirements is None:
            raise ValueError("저장된 분석 결과가 없어요. 분석 단계부터 다시 시작해 주세요.")
        req = StructuredRequirements.model_validate(requirements)
        design = create_draft(req)
    except ValueError as exc:
        reason = str(exc)
        db.add_event(job_id, job["state"], "design_error", {"reason": reason, "retryable": False})
        return {"job": fail_job(job_id, reason), "error": reason}
    design["requirements_event_index"] = max(i for i, e in enumerate(events) if e["kind"] == "requirements")
    db.add_event(job_id, job["state"], "design", design)
    return {"job": job, "design": design}

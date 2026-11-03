"""팀장: 전체 단계를 상태 머신으로 관리하고 결과를 jobs/job_events에 기록한다.

AI 판단(분석·설계·검증·수정)은 Copilot Studio 에이전트가 하고, 이 모듈은 에이전트가 API로 보낸
결과를 받아 규칙대로 상태를 넘긴다. DESIGNING 이후는 다음 이슈에서 채울 자리(stub)다.
"""
from .. import db
from ..contracts import JOB_TRANSITIONS as TRANSITIONS
from ..schemas import ProjectInput
from .analyzer import finalize
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
    """최신 분석 결과로 초안을 한 번 저장한다. 성공해도 DESIGNING 상태를 유지한다."""
    from pydantic import ValidationError

    from ..contracts import StructuredRequirements
    from ..plc.design import DesignError, DesignResult, design_circuit
    from ..plc.directives import with_auto_directives

    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "DESIGNING":
        raise InvalidTransition(f"{job['state']} 상태에서는 설계 초안을 만들 수 없어요.")
    events = db.list_events(job_id)
    try:
        stored = next((event for event in reversed(events) if event["kind"] == "design"), None)
        if stored is not None:
            design = DesignResult.model_validate(stored["data"])
            return {"job": job, "design": design.model_dump()}
        requirements = next((event for event in reversed(events) if event["kind"] == "requirements"), None)
        if requirements is None:
            raise DesignError("조건 ID 미확인: 저장된 분석 결과(requirements)가 없어요.")
        req = StructuredRequirements.model_validate(requirements["data"])
        req, skipped = with_auto_directives(req)
        try:
            design = design_circuit(req)
        except DesignError as exc:
            if skipped:
                hint = "; ".join(f"{cid}: {why}" for cid, why in skipped.items())
                raise DesignError(f"{exc} (자동 지시 생략 이유 - {hint})") from exc
            raise
    except (DesignError, ValidationError) as exc:
        reason = str(exc) if isinstance(exc, DesignError) else (
            "조건 ID 미확인: 저장된 분석·설계 결과의 계약 형식이 잘못됐어요: "
            + "; ".join(".".join(map(str, issue["loc"])) + " " + issue["msg"] for issue in exc.errors())
        )
        db.add_event(job_id, "DESIGNING", "design_error", {"reason": reason})
        return {"job": fail_job(job_id, reason), "design": None, "reason": reason}
    data = design.model_dump()
    db.add_event(job_id, "DESIGNING", "design", data)
    return {"job": job, "design": data}

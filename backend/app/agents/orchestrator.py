"""팀장: 전체 단계를 상태 머신으로 관리하고 결과를 jobs/job_events에 기록한다.

AI 판단(분석·설계·검증·수정)은 Copilot Studio 에이전트가 하고, 이 모듈은 에이전트가 API로 보낸
결과를 받아 규칙대로 상태를 넘긴다. DESIGNING 이후는 다음 이슈에서 채울 자리(stub)다.
"""
import os

from .. import db
from ..contracts import JOB_TRANSITIONS as TRANSITIONS
from ..schemas import ProjectInput
from .analyzer import MAX_QUESTIONS, finalize
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
    if job["state"] == "FIXING":
        return give_up_fix(job_id, reason)
    if "FAILED" not in TRANSITIONS[job["state"]]:
        return job
    return _move(job, "FAILED", "error", {"reason": reason})


def give_up_fix(job_id: str, reason: str) -> dict:
    """수정 에이전트가 응답하지 못할 때 FIXING에서 사람 확인(ESCALATED)으로 넘긴다."""
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "FIXING":
        return job
    job = _move(job, "VERIFYING", "fix_failed", {"reason": reason})
    return _move(job, "ESCALATED", "escalated", {"reason": reason})


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
        return _move(job, "ESCALATED", "escalated", {
            "max_iter": job["max_iter"],
            "reason": f"자동 수정을 {job['max_iter']}번 시도했지만 검증을 통과하지 못했어요. 사람이 확인해 주세요.",
        })
    return _move(job, "FIXING", "fix_requested", {"iteration": job["iteration"] + 1}, job["iteration"] + 1)


MAX_DESIGN_TRIES = 5
def fix_enabled() -> bool:
    """수정 에이전트(Studio)를 만든 뒤 환경변수 FIX_ENABLED=1로 켠다. 꺼져 있으면 검증 실패는 바로 사람 확인."""
    return os.environ.get("FIX_ENABLED") == "1"


VERIFY_NOTICE = "개발용 모의 실행 기준이에요. GX Simulator·실제 PLC 검증이 아니며, 실제 설비 적용 전 전문가 확인이 필요해요."
NOT_PROVEN = {"UNVERIFIABLE", "INVALID_CHECK"}


def _condition_rows(req, result) -> tuple[list[dict], list[dict]]:
    """조건별 결과표와, 조건에 속하지 않는 문제 목록을 만든다."""
    rows = []
    for c in req.conditions:
        errs = [e for e in result.errors if e.condition_id == c.id]
        notes = [w.message for w in result.warnings if w.condition_id == c.id and w.code in {"COVERAGE_GAP", "CUSTOM_CHECK_LOW_CONFIDENCE"}]
        passed = any(w.code == "CONDITION_PASSED" and w.condition_id == c.id for w in result.warnings)
        if errs and all(e.code in NOT_PROVEN for e in errs):
            status, message = "UNVERIFIED", errs[0].message
        elif errs:
            status, message = "FAIL", errs[0].message
        elif passed:
            status, message = "PASS", ""
        else:
            status, message = "UNVERIFIED", "이 조건은 시험 대본이 없어 검증하지 못했어요."
        rung = next((e.rung_id for e in errs if e.rung_id), "")
        rows.append({"id": c.id, "text": c.text, "must_pass": c.must_pass, "status": status,
                     "message": message, "rung_id": rung, "notes": notes})
    extra = [{"message": e.message, "rung_id": e.rung_id} for e in result.errors
             if not any(e.condition_id == c.id for c in req.conditions)]
    return rows, extra


def run_verification(job_id: str) -> dict:
    """저장된 설계를 조건의 check로 판정한다. 통과하면 COMPLETED, 아니면 수정 또는 사람 확인으로 넘긴다."""
    from ..contracts import Ir
    from ..plc.verify import verify_with_checks

    job, events = _designing_job(job_id)
    req = _requirements(events)
    design = next((e["data"] for e in reversed(events) if e["kind"] == "design"), None)
    job = _move(job, "VERIFYING", "verifying")
    try:
        result = verify_with_checks(req, Ir.model_validate(design["ir"]))
        rows, extra = _condition_rows(req, result)
    except Exception as exc:  # 판정 코드 오류로 작업이 VERIFYING에 멈추지 않게 한다
        db.add_event(job_id, "VERIFYING", "verification_error", {"reason": f"검증 중 오류가 났어요. ({type(exc).__name__})"})
        return _move(job, "ESCALATED", "escalated", {"reason": "verification_error"})
    db.add_event(job_id, "VERIFYING", "verification", {
        "passed": result.passed, "conditions": rows, "problems": extra, "notice": VERIFY_NOTICE,
    })
    if result.passed or fix_enabled():
        return report_verification(job_id, result.passed)
    return _move(job, "ESCALATED", "escalated", {"reason": "검증에 실패했어요. 자동 수정은 아직 준비 중이에요."})


def _designing_job(job_id: str) -> tuple[dict, list[dict]]:
    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "DESIGNING":
        raise InvalidTransition(f"{job['state']} 상태에서는 설계를 받을 수 없어요.")
    return job, db.list_events(job_id)


def _requirements(events: list[dict]):
    from ..contracts import StructuredRequirements

    found = next((e for e in reversed(events) if e["kind"] == "requirements"), None)
    return StructuredRequirements.model_validate(found["data"]) if found else None


def get_design_input(job_id: str) -> dict:
    """설계 에이전트가 읽을 분석 결과(조건·I/O·설정)."""
    job, events = _designing_job(job_id)
    req = _requirements(events)
    if req is None:
        raise InvalidTransition("저장된 분석 결과가 없어요.")
    return {"job": job, "requirements": req.model_dump()}


def check_design_ir(job_id: str, ir: dict) -> tuple[object | None, list[str]]:
    """저장 없이 회로(IR)만 검사한다. (결과, 고칠 점)을 돌려준다."""
    from pydantic import ValidationError

    from ..contracts import Ir
    from ..plc.design_check import check_design

    _, events = _designing_job(job_id)
    req = _requirements(events)
    if req is None:
        return None, ["저장된 분석 결과가 없어요."]
    try:
        parsed = Ir.model_validate(ir)
    except ValidationError as exc:
        return None, ["[IR_FORMAT] " + ".".join(map(str, i["loc"])) + " " + i["msg"] for i in exc.errors()]
    return check_design(req, parsed)


def submit_design(job_id: str, ir: dict) -> dict:
    """설계 에이전트의 회로를 검사해 통과하면 저장한다. 거부되면 고칠 점을 돌려주고, 5번 거부되면 FAILED."""
    design, problems = check_design_ir(job_id, ir)
    job, events = _designing_job(job_id)
    if design is not None:
        data = design.model_dump()
        db.add_event(job_id, "DESIGNING", "design", data)
        return {"job": run_verification(job_id), "ok": True, "design": data, "errors": []}
    db.add_event(job_id, "DESIGNING", "design_rejected", {"errors": problems})
    tries = sum(1 for e in events if e["kind"] == "design_rejected") + 1
    if tries >= MAX_DESIGN_TRIES:
        reason = f"설계가 {tries}번 거부됐어요: " + "; ".join(problems[:3])
        db.add_event(job_id, "DESIGNING", "design_error", {"reason": reason})
        job = fail_job(job_id, reason)
    return {"job": job, "ok": False, "design": None, "errors": problems}


ROOT_CAUSES = {
    "UNMET_CONDITION": "회로가 조건이 요구하는 동작을 만들지 못했어요.",
    "UNVERIFIABLE": "조건을 모의 실행으로 확인할 수 없는 회로였어요.",
}


def _fixing_context(job_id: str):
    """FIXING 작업의 (job, requirements, 현재 회로, 그 회로의 검증 결과)."""
    from ..contracts import Ir
    from ..plc.verify import verify_with_checks

    job = db.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] != "FIXING":
        raise InvalidTransition(f"{job['state']} 상태에서는 수정 요청을 처리할 수 없어요.")
    events = db.list_events(job_id)
    req = _requirements(events)
    design = next((e["data"] for e in reversed(events) if e["kind"] == "design"), None)
    if req is None or design is None:
        raise InvalidTransition("저장된 분석 결과나 설계가 없어요.")
    ir = Ir.model_validate(design["ir"])
    return job, req, ir, verify_with_checks(req, ir)


def _first_failure(req, result):
    for e in result.errors:
        cond = next((c for c in req.conditions if c.id == e.condition_id), None)
        if cond is not None:
            return cond, e
    return None, None


def get_fix_input(job_id: str) -> dict:
    """수정 에이전트가 읽을 수정 요청(실패 조건·지킬 조건·현재 회로·같은 시리즈의 검증된 사례)."""
    from ..plc.error_knowledge import build_signature, find_similar
    from ..plc.fix_request import build_fix_request

    job, req, ir, result = _fixing_context(job_id)
    cases: list[dict] = []
    cond, err = _first_failure(req, result)
    if cond is not None:
        try:
            cases = find_similar(req.plc_config.series, build_signature(req.plc_config.series, cond.type, err.code), [])
        except ValueError:
            cases = []
    return {"job": job, "fix_request": build_fix_request(req, ir, result, cases)}


def _save_knowledge(job: dict, req, before, check, attempt: int) -> None:
    """검증을 통과한 수정만 저장한다. 문장은 코드가 정한 틀로만 채워 자유 입력이 섞이지 않게 한다."""
    from ..plc.error_knowledge import build_signature, save_verified_fix

    cond, err = _first_failure(req, before)
    if cond is None:
        return
    series = req.plc_config.series
    d = check.diff
    try:
        save_verified_fix(
            check, job["project_id"], f"{job['id']}-{attempt - 1}", f"{job['id']}-{attempt}", series,
            build_signature(series, cond.type, err.code),
            f"{cond.type} 조건이 {err.code} 오류로 실패했어요.",
            ROOT_CAUSES.get(err.code, "회로가 조건을 만족하지 못했어요."),
            f"{err.code} 해결: 렁 {len(d['changed'])}개 변경, {len(d['added'])}개 추가, {len(d['removed'])}개 삭제.",
            privacy_reviewed=True,
        )
    except Exception as exc:  # 사례 저장이 실패해도 수정 결과는 그대로 둔다
        db.add_event(job["id"], "COMPLETED", "knowledge_skipped", {"reason": type(exc).__name__})


def submit_fix(job_id: str, ir: dict, reason: str = "") -> dict:
    """수정 에이전트의 회로를 코드가 다시 검증한다. 통과하면 COMPLETED, 아니면 다음 시도(또는 ESCALATED)."""
    from ..plc.design_check import check_design
    from ..plc.fix_check import check_fix

    job, req, old_ir, before = _fixing_context(job_id)
    attempt = job["iteration"]
    check = check_fix(req, old_ir, ir, before)
    if not check.ok:
        db.add_event(job_id, "FIXING", "fix_rejected", {"attempt": attempt, "reason": check.reason})
        job = _move(job, "VERIFYING", "verifying")
        rows, extra = _condition_rows(req, before)
        db.add_event(job_id, "VERIFYING", "verification", {
            "passed": False, "conditions": rows, "problems": extra, "notice": VERIFY_NOTICE,
        })
        return {"job": report_verification(job_id, False), "ok": False, "reason": check.reason,
                "diff": check.diff, "errors": [check.reason]}
    design, _ = check_design(req, check.new_ir)
    db.add_event(job_id, "FIXING", "fix_applied", {
        "attempt": attempt, "reason": check.reason, "agent_reason": reason[:500], "diff": check.diff,
    })
    db.add_event(job_id, "FIXING", "design", design.model_dump())
    job = _move(job, "VERIFYING", "verifying")
    rows, extra = _condition_rows(req, check.result)
    db.add_event(job_id, "VERIFYING", "verification", {
        "passed": True, "conditions": rows, "problems": extra, "notice": VERIFY_NOTICE,
    })
    job = report_verification(job_id, True)
    _save_knowledge(job, req, before, check, attempt)
    return {"job": job, "ok": True, "reason": check.reason, "diff": check.diff, "errors": []}

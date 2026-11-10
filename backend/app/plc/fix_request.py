"""수정 에이전트 입력을 만든다. 에이전트를 호출하거나 회로를 고치지 않는다."""
from ..contracts import Ir, StructuredRequirements, VerificationResult

MAX_MESSAGE_LENGTH = 1000
MAX_CASES = 5
MAX_ISSUES = 64
INFORMATION_CODES = {"CONDITION_PASSED", "COVERAGE_GAP", "CUSTOM_CHECK_LOW_CONFIDENCE"}


def passed_condition_ids(result: VerificationResult) -> set[str]:
    """PASS 안내가 있어도 같은 조건에 실패가 있으면 통과로 취급하지 않는다."""
    passed = {w.condition_id for w in result.warnings if w.code == "CONDITION_PASSED"}
    failed = {e.condition_id for e in result.errors}
    failed.update(w.condition_id for w in result.warnings if w.code not in INFORMATION_CODES)
    return passed - failed - {""}


def build_fix_request(
    req: StructuredRequirements, ir: Ir, result: VerificationResult,
    similar_cases: list[dict] | None = None,
) -> dict:
    """현재 IR은 보존하고 자유 문장·문제·사례는 상한과 잘림 표시를 제공한다."""
    truncated = False

    def text(value: str) -> str:
        nonlocal truncated
        if len(value) > MAX_MESSAGE_LENGTH:
            truncated = True
            return value[:MAX_MESSAGE_LENGTH - 1] + "…"
        return value

    by_id = {c.id: c for c in req.conditions}
    issues = list(result.errors) + [w for w in result.warnings if w.code not in INFORMATION_CODES]
    truncated = len(issues) > MAX_ISSUES
    failed, problems = [], []
    for issue in issues[:MAX_ISSUES]:
        message = issue.message
        if issue.condition_id in by_id and not issue.rung_id:
            message = "이 조건을 만드는 렁이 없어요. " + message
        row = {"code": issue.code, "message": text(message), "rung_id": issue.rung_id}
        condition = by_id.get(issue.condition_id)
        if condition is None:
            problems.append({**row, "condition_id": issue.condition_id})
        else:
            failed.append({**row, "id": condition.id, "type": condition.type,
                           "text": text(condition.text), "must_pass": condition.must_pass})
    passed = passed_condition_ids(result)
    protected = [{"id": c.id, "text": text(c.text)} for c in req.conditions if c.id in passed]
    eligible = [c for c in similar_cases or []
                if c.get("plc_series") == req.plc_config.series and c.get("verified") in (True, 1)]
    if len(eligible) > MAX_CASES:
        truncated = True
    cases = []
    for case in eligible[:MAX_CASES]:
        cases.append({
            "plc_series": req.plc_config.series, "verified": True,
            **{key: text(str(case.get(key, ""))) for key in (
                "id", "error_signature", "symptom", "root_cause", "solution",
            )},
        })
    io = [{"device": r.device, "name": text(r.name), "kind": text(r.kind)} for r in req.io_list]
    return {
        "plc_series": req.plc_config.series, "failed_conditions": failed,
        "protected_conditions": protected, "problems": problems, "ir": ir.model_dump(),
        "emergency_stop": req.plc_config.emergency_stop.model_dump(), "io_list": io,
        "similar_cases": cases,
        "limits": {"message_length": MAX_MESSAGE_LENGTH, "cases": MAX_CASES,
                   "issues": MAX_ISSUES, "truncated": truncated},
    }

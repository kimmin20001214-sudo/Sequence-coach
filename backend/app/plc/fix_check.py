"""수정 결과를 코드로 재검증한다. 모의 실행 통과는 실제 설비 안전 보장이 아니다."""
from pydantic import BaseModel, Field, ValidationError

from ..contracts import Ir, StructuredRequirements, VerificationResult
from .design_check import check_design
from .fix_request import passed_condition_ids
from .ir_diff import diff_ir
from .verify import verify_with_checks


class FixCheck(BaseModel):
    ok: bool
    reason: str
    diff: dict | None = None
    result: VerificationResult | None = None
    regressions: list[str] = Field(default_factory=list)
    plc_series: str
    old_ir: Ir | None = None
    new_ir: Ir | None = None


def check_fix(
    req: StructuredRequirements, old_ir: Ir, new_ir: Ir | dict,
    before_result: VerificationResult,
) -> FixCheck:
    """형식 → 설계 → 동일 회로 거절 → 전체 재검증 → 퇴보 검사. 입력을 바꾸지 않는다."""
    series = req.plc_config.series
    try:
        # Pydantic 모델도 필드 대입으로 손상될 수 있어 원시 데이터로 다시 검사한다.
        parsed = Ir.model_validate(new_ir.model_dump() if isinstance(new_ir, Ir) else new_ir)
    except ValidationError as exc:
        locations = ["/".join(map(str, e["loc"])) for e in exc.errors()[:5]]
        return FixCheck(ok=False, reason="회로 형식이 올바르지 않아요: " + ", ".join(locations),
                        plc_series=series)
    design, problems = check_design(req, parsed)
    if design is None:
        return FixCheck(ok=False, reason="설계 검사를 통과하지 못했어요: " + "; ".join(problems[:5]),
                        plc_series=series)
    diff = diff_ir(old_ir, parsed)
    if diff["same"]:
        return FixCheck(ok=False, reason="원래 회로와 같아요. 접점·출력·연결을 실제로 고쳐 주세요.",
                        diff=diff, plc_series=series)
    result = verify_with_checks(req, parsed)
    previous = passed_condition_ids(before_result)
    current = passed_condition_ids(result)
    regressions = [c.id for c in req.conditions if c.id in previous - current]
    if regressions:
        return FixCheck(
            ok=False, reason="퇴보가 있어요: " + ", ".join(regressions) + "가 이전에는 통과했지만 지금은 통과하지 못해요.",
            diff=diff, result=result, regressions=regressions, plc_series=series,
        )
    if not result.passed:
        return FixCheck(
            ok=False, reason="전체 재검사에 실패했어요: " + "; ".join(e.message for e in result.errors[:5]),
            diff=diff, result=result, plc_series=series,
        )
    repaired = [c.id for c in req.conditions if c.id in current and any(
        e.condition_id == c.id for e in before_result.errors + before_result.warnings
        if e.code not in {"CONDITION_PASSED", "COVERAGE_GAP", "CUSTOM_CHECK_LOW_CONFIDENCE"}
    )]
    changes = [c["summary"] for c in diff["changed"]]
    changes += [f"렁 추가 {rid}" for rid in diff["added"]]
    changes += [f"렁 삭제 {rid}" for rid in diff["removed"]]
    reason = ((", ".join(repaired) + "가 고쳐졌어요. ") if repaired else "고친 회로가 통과했어요. ")
    reason += "; ".join(changes[:5])[:1000]
    reason += ". 전체 필수 조건과 이전 통과 조건을 모의 실행으로 다시 확인했어요. 실제 설비 안전을 보장하지 않아요."
    return FixCheck(ok=True, reason=reason, diff=diff, result=result, plc_series=series,
                    old_ir=old_ir.model_copy(deep=True), new_ir=parsed.model_copy(deep=True))

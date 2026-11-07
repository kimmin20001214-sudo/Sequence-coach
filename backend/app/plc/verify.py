"""AI 없이 정적 규칙과 모의 실행의 기대값을 비교한다."""
from collections.abc import Mapping

from ..contracts import Ir, StructuredRequirements, VerificationIssue, VerificationResult
from ..spec import get_series
from .design_check import TEMPORARY_LIMITS
from .rules import validate_ir
from .scenario import Scenario
from .sim import Signals, run
from .static_check import check_double_outputs

SCAN_MS = 10
SAFETY_NOTICE = (
    "개발용 모의 실행이며 GX Simulator·실제 PLC 검증이 아니에요. "
    "모의 실행 통과는 실제 설비 안전을 보장하지 않아요. 실제 설비 적용 전 전문가 확인 필요"
)


def verify(
    req: StructuredRequirements,
    ir: Ir,
    scenarios: list[dict],
    *,
    internal_limits: Mapping[str, int] | None = None,
) -> VerificationResult:
    """필수 조건은 errors, 선택 조건의 실패·검사 불가는 warnings에 기록한다."""
    warnings = [VerificationIssue(code="SIMULATION_ONLY", message=SAFETY_NOTICE)]
    if internal_limits is None:
        spec_limits = (get_series(req.plc_config.series) or {}).get("internal_limits", {})
        internal_limits = {kind: spec_limits.get(kind, end) for kind, end in TEMPORARY_LIMITS.items()}
        if any(kind not in spec_limits for kind in TEMPORARY_LIMITS):
            warnings.append(VerificationIssue(
                code="TEMPORARY_INTERNAL_LIMITS",
                message="설계 단계와 같은 매뉴얼 미확인 임시 내부 주소 범위를 사용해요. "
                        f"끝값 미포함: {dict(internal_limits)}",
            ))
    static = validate_ir(ir, req.plc_config, req.io_list, internal_limits=internal_limits)
    errors = list(static.errors)
    warnings.extend(static.warnings)
    if not errors:
        errors.extend(check_double_outputs(ir, req.io_list))
    static_failed = bool(errors)

    ids = [condition.id for condition in req.conditions]
    invalid_ids = any(not cid.strip() for cid in ids) or len(set(ids)) != len(ids)
    if invalid_ids:
        errors.append(VerificationIssue(code="UNVERIFIABLE", message="조건 ID는 비어 있지 않고 고유해야 해요."))
    if not any(condition.must_pass for condition in req.conditions):
        errors.append(VerificationIssue(code="UNVERIFIABLE", message="검사할 필수 조건이 하나 이상 필요해요."))

    grouped: dict[str, list[dict]] = {cid: [] for cid in ids}
    for raw in scenarios:
        cid = raw.get("condition_id") if isinstance(raw, dict) else None
        if not isinstance(cid, str) or cid not in grouped:
            errors.append(VerificationIssue(
                code="UNVERIFIABLE", message=f"등록된 조건 ID가 없는 시나리오예요: {cid!r}",
            ))
        else:
            grouped[cid].append(raw)

    can_run = not static_failed and not invalid_ids
    signals = Signals(req.io_list) if can_run else None

    for condition in req.conditions:
        issues: list[VerificationIssue] = []
        summaries: list[str] = []
        matching = grouped[condition.id]

        def unavailable(message: str) -> None:
            issues.append(VerificationIssue(
                code="UNVERIFIABLE", message=message, condition_id=condition.id,
            ))

        if not can_run:
            unavailable("정적 검사 또는 조건 ID 오류로 동작을 검사하지 않았어요.")
        elif not matching:
            unavailable("이 조건의 검사 시나리오가 없어요.")
        else:
            assert signals is not None
            for raw in matching:
                try:
                    scenario = Scenario.model_validate(raw)
                    expected_devices = []
                    for expected in scenario.expect:
                        if expected.t_ms % SCAN_MS:
                            raise ValueError(f"기대 시각은 {SCAN_MS}ms 스캔 간격의 배수여야 해요.")
                        expected_devices.append(signals.resolve(expected.dev))
                    end = max([s.t_ms for s in scenario.steps] + [e.t_ms for e in scenario.expect])
                    trace = run(
                        ir, [s.model_dump() for s in scenario.steps], io_list=req.io_list,
                        until_ms=end, scan_ms=SCAN_MS,
                    )
                    if any(dev not in trace[0]["state"] for dev in expected_devices):
                        raise ValueError("회로에 정의되지 않은 내부 신호의 기대값은 검사할 수 없어요.")
                except ValueError as exc:
                    unavailable(f"조건 {condition.id} 검사 불가: {exc}")
                    continue
                for expected, dev in zip(scenario.expect, expected_devices):
                    actual = int(trace[expected.t_ms // SCAN_MS]["state"][dev])
                    detail = f"{dev}: 기대값 {int(expected.value)}, 실제값 {actual}, 시각 {expected.t_ms}ms"
                    if actual != expected.value:
                        producer = next((
                            rung.id for rung in ir.rungs
                            if any(signals.resolve(output.target) == dev for output in rung.outputs)
                        ), "")
                        issues.append(VerificationIssue(
                            code="UNMET_CONDITION",
                            message=f"조건 {condition.id} 실패 — {detail}",
                            rung_id=producer, condition_id=condition.id,
                        ))
                    else:
                        summaries.append(detail)
        if issues:
            (errors if condition.must_pass else warnings).extend(issues)
        else:
            warnings.append(VerificationIssue(
                code="CONDITION_PASSED", condition_id=condition.id,
                message=f"조건 {condition.id}의 모든 시나리오가 통과했어요. " + "; ".join(summaries),
            ))
    return VerificationResult(passed=not errors, errors=errors, warnings=warnings)

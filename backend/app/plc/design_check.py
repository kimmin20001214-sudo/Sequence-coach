"""설계 에이전트가 낸 회로(IR)를 코드로 검사하고 IL로 바꾼다. AI도 문장 해석도 없다."""
from pydantic import BaseModel

from ..contracts import Contact, Ir, Node, StructuredRequirements
from ..schemas import IoRow
from ..spec import get_series
from .rules import validate_ir
from .to_il import IrConversionError, to_il

SAFETY_NOTICE = "설계 초안이며 안전 검토를 수행하지 않았어요. 실제 설비 적용 전 전문가 확인 필요"
# 매뉴얼 미확인 임시값. 끝값은 미포함이며 PLC의 실제 허용 범위를 보증하지 않는다.
TEMPORARY_LIMITS = {"M": 8192, "T": 2048, "C": 1024}


class DesignResult(BaseModel):
    ir: Ir
    io_used: list[IoRow]
    explanation: list[dict]
    assumptions: list[str]
    limitations: list[str]
    il: list[str]


def _contacts(node: Node) -> list[Contact]:
    if isinstance(node, Contact):
        return [node]
    return [leaf for child in node.items for leaf in _contacts(child)]


def check_design(req: StructuredRequirements, ir: Ir) -> tuple[DesignResult | None, list[str]]:
    """통과하면 (결과, []), 거부되면 (None, 고칠 점 목록)을 돌려준다."""
    cfg = req.plc_config
    if cfg.series != "Q" or cfg.language != "ladder":
        return None, ["Q시리즈 래더만 설계할 수 있어요."]
    if cfg.retentive or cfg.alarm or cfg.modules or cfg.modes != ["자동"]:
        return None, ["보존·경보·추가 모듈·다중 운전 모드는 아직 설계하지 못해요."]

    limitations = [SAFETY_NOTICE]
    spec_limits = (get_series(cfg.series) or {}).get("internal_limits", {})
    limits = {kind: spec_limits.get(kind, end) for kind, end in TEMPORARY_LIMITS.items()}
    if any(kind not in spec_limits for kind in limits):
        limitations.append("내부 주소 끝값은 매뉴얼 미확인 임시값(M8192/T2048/C1024, 끝값 미포함)이에요.")

    result = validate_ir(ir, cfg, req.io_list, internal_limits=limits)
    problems = [f"[{i.code}] {i.message}" + (f" (렁 {i.rung_id})" if i.rung_id else "") for i in result.errors]

    covered = {cid for rung in ir.rungs for cid in rung.covers}
    for cond in req.conditions:
        if (cond.must_pass or cond.type == "safety") and cond.id not in covered:
            problems.append(f"[UNMET_CONDITION] 조건 {cond.id}를 만족시키는 렁이 없어요. 렁의 covers에 조건 id를 적어 주세요.")

    rows = {}
    for row in req.io_list:
        rows[row.device.strip().upper()] = row
        rows[row.name.strip().upper()] = row
    # 푸시버튼은 설정한 종류대로 접점을 쓴다: NO는 a접점, NC는 b접점 (이름과 무관).
    for rung in ir.rungs:
        for c in _contacts(rung.condition):
            row = rows.get(c.signal.strip().upper())
            if row is None or "푸시버튼" not in row.kind:
                continue
            want = "NC" if "NC" in row.kind.upper() else "NO"
            if c.kind != want:
                label = "b접점(NC)" if want == "NC" else "a접점(NO)"
                problems.append(f"[KIND_MISMATCH] {row.device}는 {row.kind}라서 {label}으로 써야 해요.                 (단 {rung.id})")
    def kind_of(signal: str) -> str:
        row = rows.get(signal.strip().upper())
        return (row.device if row else signal).strip().upper()[:1]

    # 입력부(X 접점 → 내부 릴레이 M)와 출력부(M 접점 → 출력 Y)를 나눈다.
    in_output_part = False
    for rung in ir.rungs:
        drives_y = any(kind_of(o.target) == "Y" for o in rung.outputs)
        if drives_y:
            in_output_part = True
            if any(kind_of(o.target) != "Y" for o in rung.outputs):
                problems.append(f"[IO_SPLIT] 단 {rung.id}: 출력 Y 코일은 M·T 같은 다른 출력과 한 렁에 섞지 말고 출력부에 따로 두세요.")
            if any(kind_of(c.signal) == "X" for c in _contacts(rung.condition)):
                problems.append(f"[IO_SPLIT] 단 {rung.id}: 출력 Y는 입력 X를 직접 쓰지 말고 입력부의 내부 릴레이 M 접점으로 구동하세요.")
        elif in_output_part:
            problems.append(f"[IO_SPLIT] 단 {rung.id}: 입력부 렁(M·T·C 출력)은 출력부(Y) 렁보다 앞에 두세요.")

    estop = cfg.emergency_stop
    if estop.used:
        stop_row = rows.get(estop.device.strip().upper())
        want = "NC"
        label = "NC 접점(b접점)"
        for rung in ir.rungs:
            if not any(kind_of(c.signal) == "X" for c in _contacts(rung.condition)):
                continue
            names = {c.signal.strip().upper() for c in _contacts(rung.condition) if c.kind == want}
            if stop_row is None or not names & {stop_row.device.strip().upper(), stop_row.name.strip().upper()}:
                problems.append(f"[ESTOP_MISSING] 비상정지 {estop.device}가 렁 {rung.id}에 {label}으로 직렬 연결되어야 해요.")
    if problems:
        return None, problems

    try:
        il = to_il(ir, cfg, req.io_list, internal_limits=limits)
    except IrConversionError as exc:
        return None, [f"[{i.code}] {i.message}" for i in exc.result.errors]
    limitations.extend(w.message for w in result.warnings if w.message not in limitations)

    used = set()
    explanation = []
    for rung in ir.rungs:
        used.update(c.signal.strip().upper() for c in _contacts(rung.condition))
        used.update(o.target.strip().upper() for o in rung.outputs)
        explanation.append({"rung_id": rung.id, "condition_ids": rung.covers.copy(),
                            "text": rung.comment or "(설명 없음)"})
    seen, io_used = set(), []
    for row in req.io_list:
        keys = {row.device.strip().upper(), row.name.strip().upper()}
        if keys & used and row.device not in seen:
            seen.add(row.device)
            io_used.append(row.model_copy(deep=True))
    return DesignResult(ir=ir, io_used=io_used, explanation=explanation, assumptions=req.assumptions.copy(),
                        limitations=limitations, il=il), []

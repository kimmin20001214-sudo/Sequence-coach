"""명시적인 design.v1 지시로만 만드는 Q 래더 설계 초안."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ..contracts import Contact, Ir, Node, Output, Parallel, Rung, Series, StructuredRequirements
from ..schemas import IoRow
from ..spec import get_series, parse_device
from .rules import validate_ir
from .to_il import IrConversionError, to_il

PREFIX = "design.v1:"
SAFETY_NOTICE = "설계 초안이며 안전 검토를 수행하지 않았어요. 실제 설비 적용 전 전문가 확인 필요"
# 매뉴얼 미확인 임시값. #63과 동일하게 끝값은 미포함이며 PLC의 실제 허용 범위를 보증하지 않는다.
TEMPORARY_LIMITS = {"M": 8192, "T": 2048, "C": 1024}


class DesignError(ValueError):
    pass


class DesignResult(BaseModel):
    ir: Ir
    io_used: list[IoRow]
    explanation: list[dict]
    assumptions: list[str]
    limitations: list[str]
    il: list[str]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    signal: str
    active: Literal["on", "off"]


class _Directive(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    condition_id: str
    mode: Literal["direct", "self_hold", "on_delay", "count", "block", "emergency_stop"]
    inputs: list[_Input] = []
    join: Literal["all", "any"] | None = None
    outputs: list[str] = []
    timer: str | None = None
    counter: str | None = None
    reset: Literal["none"] | None = None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DesignError(f"설계 지시의 {key} 항목이 중복돼요.")
        result[key] = value
    return result


def _group(items: list[Node], join: str) -> Node:
    if len(items) == 1:
        return items[0]
    return Series(items=items) if join == "all" else Parallel(items=items)


def _not(node: Node) -> Node:
    if isinstance(node, Contact):
        return Contact(signal=node.signal, kind="NC" if node.kind == "NO" else "NO")
    cls = Parallel if isinstance(node, Series) else Series
    return cls(items=[_not(child) for child in node.items])


def _contacts(node: Node) -> list[Contact]:
    if isinstance(node, Contact):
        return [node]
    return [leaf for child in node.items for leaf in _contacts(child)]


def design_circuit(req: StructuredRequirements) -> DesignResult:
    """AI·문장 해석·상태 저장 없이 명시 지시를 설계하고 validate_ir → to_il로 검사한다."""
    ids = [condition.id for condition in req.conditions]
    context = ", ".join(ids) or "조건 없음"

    def error(message: str, condition_id: str = context) -> None:
        raise DesignError(f"조건 {condition_id}: {message}")

    if req.questions:
        error("답하지 않은 질문이 남아 있어요: " + "; ".join(req.questions))
    if not ids or any(not cid or cid != cid.strip() for cid in ids) or len(set(ids)) != len(ids):
        error("조건 ID는 비어 있지 않고 중복 없이 지정해야 해요.")
    cfg = req.plc_config
    if cfg.series != "Q" or cfg.language != "ladder":
        error("Q시리즈 래더만 설계할 수 있어요.")
    if cfg.retentive or cfg.alarm or cfg.modules or cfg.modes != ["자동"]:
        error("보존·경보·추가 모듈·다중 운전 모드는 아직 설계하지 못해요.")

    limitations = [SAFETY_NOTICE]
    spec = get_series(cfg.series) or {}
    spec_limits = spec.get("internal_limits", {})
    limits = {kind: spec_limits.get(kind, end) for kind, end in TEMPORARY_LIMITS.items()}
    missing_limits = [kind for kind in limits if kind not in spec_limits]
    if missing_limits:
        labels = "/".join(f"{kind}{limits[kind]}" for kind in missing_limits)
        limitations.append(f"내부 끝값은 매뉴얼 미확인 임시값({labels}, 끝값 미포함)이에요.")
    rows: dict[str, IoRow] = {}
    aliases: dict[str, str] = {}
    for row in req.io_list:
        parsed = parse_device(row.device, "hex")
        if not parsed or not row.name.strip():
            error(f"등록 I/O {row.device}의 주소·이름을 확인해 주세요.")
        address = f"{parsed[0]}{parsed[1]:X}"
        if address in rows:
            error(f"{address} I/O 주소가 중복돼요.")
        rows[address] = row
        for token in (row.device.strip().upper(), row.name.strip().upper()):
            direct = parse_device(token, "hex")
            if (token in aliases and aliases[token] != address) or (
                direct and f"{direct[0]}{direct[1]:X}" != address
            ):
                error(f"{token} 신호 이름·주소가 충돌해요.")
            aliases[token] = address

    def resolve(signal: str, cid: str) -> str:
        token = signal.strip().upper()
        parsed = parse_device(token, "hex")
        dev = aliases.get(token) or (f"{parsed[0]}{parsed[1]:X}" if parsed else "")
        if dev not in rows:
            error(f"{signal} 신호가 I/O 목록에 등록되어 있지 않아요.", cid)
        return dev

    conditions = {condition.id: condition for condition in req.conditions}
    signals = {
        c.id: [resolve(signal, c.id) for signal in c.signals] for c in req.conditions
    }
    for cid, devices in signals.items():
        if not devices or len(set(devices)) != len(devices):
            error("조건 signals는 비어 있지 않고 같은 신호를 중복해서 적지 않아야 해요.", cid)

    directives: dict[str, _Directive] = {}
    for text in req.assumptions:
        if not text.startswith(PREFIX):
            continue
        try:
            raw = json.loads(text[len(PREFIX):], object_pairs_hook=_unique_object)
            directive = _Directive.model_validate(raw)
        except (ValueError, ValidationError) as exc:
            error(f"설계 지시 형식이 잘못됐어요: {exc}")
        cid = directive.condition_id
        if cid not in conditions:
            error("설계 지시의 조건 ID를 찾을 수 없어요.", cid)
        if cid in directives:
            error("한 조건에 설계 지시가 중복돼요.", cid)
        common = {"condition_id", "mode", "inputs", "join", "outputs"}
        required = {
            "direct": common, "self_hold": common, "block": common,
            "on_delay": common | {"timer"}, "count": common | {"counter", "reset"},
            "emergency_stop": {"condition_id", "mode"},
        }[directive.mode]
        if set(raw) != required:
            error(f"{directive.mode} 지시에 필요한 항목만 빠짐없이 지정해 주세요: {sorted(required)}", cid)
        expected_type = {
            "direct": "sequence", "self_hold": "sequence", "block": "interlock",
            "on_delay": "timing", "count": "sequence", "emergency_stop": "safety",
        }[directive.mode]
        if conditions[cid].type != expected_type:
            error(f"{directive.mode}는 {expected_type} 조건에만 사용할 수 있어요.", cid)
        if directive.mode != "emergency_stop":
            if not directive.inputs or not directive.outputs or directive.join is None:
                error("입력·출력·입력 연결 방식(all/any)을 명시해 주세요.", cid)
            directive = directive.model_copy(deep=True)
            for item in directive.inputs:
                item.signal = resolve(item.signal, cid)
                row = rows[item.signal]
                if item.signal.startswith("X") and row.kind not in {
                    "푸시버튼 NO", "푸시버튼 NC", "센서", "리미트스위치",
                }:
                    error(f"{item.signal}의 입력 종류(kind)를 확정해 주세요.", cid)
            directive.outputs = [resolve(out, cid) for out in directive.outputs]
            if any(not out.startswith("Y") or rows[out].kind not in {
                "솔레노이드", "모터", "램프",
            } for out in directive.outputs):
                error("출력은 등록된 Y 주소와 솔레노이드·모터·램프 종류여야 해요.", cid)
            used = [item.signal for item in directive.inputs] + directive.outputs
            if len(set(used)) != len(used) or set(used) != set(signals[cid]):
                error("입력·출력은 조건 signals 전체와 일치하며 서로 중복되지 않아야 해요.", cid)
        directives[cid] = directive
    for cid in ids:
        if cid not in directives:
            error("명시적인 design.v1 설계 지시가 없어서 동작을 확정할 수 없어요.", cid)

    def logic(rule: _Directive) -> Node:
        assert rule.join is not None
        return _group([
            Contact(signal=item.signal, kind="NO" if item.active == "on" else "NC")
            for item in rule.inputs
        ], rule.join)

    safety = [d for d in directives.values() if d.mode == "emergency_stop"]
    emergency: Contact | None = None
    if cfg.emergency_stop.used:
        if len(safety) != 1:
            error("비상정지 사용 시 모든 출력 OFF를 담당하는 safety 지시가 하나 필요해요.")
        cid = safety[0].condition_id
        dev = resolve(cfg.emergency_stop.device, cid)
        if signals[cid] != [dev] or not dev.startswith("X") or rows[dev].kind != "푸시버튼 NC":
            error("비상정지는 평상시 ON인 NC 물리 버튼 하나로 명시해야 해요.", cid)
        emergency = Contact(signal=dev, kind="NO")
    elif safety:
        error("비상정지 사용 설정 없이 safety 지시를 적용할 수 없어요.", safety[0].condition_id)

    producers: dict[str, str] = {}
    blocks: dict[str, list[_Directive]] = {}
    for cid, rule in directives.items():
        if rule.mode == "block":
            for out in rule.outputs:
                blocks.setdefault(out, []).append(rule)
        elif rule.mode != "emergency_stop":
            for out in rule.outputs:
                if out in producers:
                    error(f"{out} 출력을 여러 조건에서 구동할 수 없어요.", cid)
                producers[out] = cid
    for out, rules in blocks.items():
        if out not in producers:
            error(f"{out} 출력의 구동 조건이 없어 인터록을 실질 반영할 수 없어요.", rules[0].condition_id)
    for cid, rule in directives.items():
        for item in rule.inputs:
            if item.signal.startswith("Y") and item.signal not in producers:
                error(f"{item.signal} 출력의 구동 조건이 없어요.", cid)

    timers = {timer.name: timer for timer in req.timers}
    counters = {counter.name: counter for counter in req.counters}
    if any(not name or name != name.strip() for name in [*timers, *counters]) or (
        len(timers) != len(req.timers) or len(counters) != len(req.counters)
    ):
        error("타이머·카운터 이름은 비어 있지 않고 중복 없이 지정해야 해요.")
    used_timers: set[str] = set()
    used_counters: set[str] = set()
    next_device = cfg.device_rule.model_dump()

    def allocate(kind: str, cid: str) -> str:
        number = next_device[kind]
        if type(number) is not int or type(limits[kind]) is not int or not 0 <= number < limits[kind]:
            error(f"{kind} 내부 주소가 설정 시작 번호·끝값 범위를 벗어나요.", cid)
        next_device[kind] += 1
        return f"{kind}{number}"

    def gated(node: Node, outputs: list[str], cid: str) -> tuple[Node, list[str]]:
        covers = [cid]
        items = [node]
        for out in outputs:
            for rule in blocks.get(out, []):
                if rule.condition_id not in covers:
                    items.append(_not(logic(rule)))
                    covers.append(rule.condition_id)
        if emergency:
            items.append(emergency.model_copy())
            covers.append(safety[0].condition_id)
        return _group(items, "all"), covers

    rungs: list[Rung] = []

    def add(node: Node, outputs: list[Output], covers: list[str]) -> None:
        rungs.append(Rung(id=f"R{len(rungs) + 1}", condition=node, outputs=outputs, covers=covers))

    pending = [d for d in directives.values() if d.mode not in {"block", "emergency_stop"}]
    done: set[str] = set()
    while pending:
        ready = next((d for d in pending if all(
            not item.signal.startswith("Y") or producers[item.signal] in done for item in d.inputs
        )), None)
        if ready is None:
            error("출력 참조가 순환해서 실행 순서를 확정할 수 없어요.", ", ".join(d.condition_id for d in pending))
        rule = ready
        cid = rule.condition_id
        node = logic(rule)
        gate_sets = [{b.condition_id for b in blocks.get(out, [])} for out in rule.outputs]
        if any(gates != gate_sets[0] for gates in gate_sets):
            error("함께 구동하는 출력의 정지·인터록 지시는 같아야 해요. 조건을 나눠 주세요.", cid)
        if rule.mode == "self_hold":
            # 여러 출력은 M 접점 하나로 함께 유지한다. 서로 다른 인터록은 별도 조건으로 나눠야 한다.
            hold = rule.outputs[0] if len(rule.outputs) == 1 else allocate("M", cid)
            node = Parallel(items=[node, Contact(signal=hold, kind="NO")])
            if len(rule.outputs) > 1:
                node, covers = gated(node, rule.outputs, cid)
                add(node, [Output(kind="OUT", target=hold)], covers)
                node = Contact(signal=hold, kind="NO")
        elif rule.mode in {"on_delay", "count"}:
            is_timer = rule.mode == "on_delay"
            name = rule.timer if is_timer else rule.counter
            specs = timers if is_timer else counters
            used_specs = used_timers if is_timer else used_counters
            if name not in specs or name in used_specs:
                error(f"{name} 타이머·카운터 연결이 없거나 중복돼요.", cid)
            if not is_timer and rule.reset != "none":
                error("카운터는 명시적인 reset=none 초안만 지원해요.", cid)
            used_specs.add(name)
            device = allocate("T" if is_timer else "C", cid)
            preset = specs[name]
            output = (
                Output(kind="TON", target=device, preset_ms=preset.preset_ms)
                if is_timer else Output(kind="CTU", target=device, preset=preset.preset)
            )
            node, covers = gated(node, rule.outputs, cid)
            add(node, [output], covers)
            node = Contact(signal=device, kind="NO")
            if not is_timer:
                limitations.append(f"조건 {cid}: 카운터 {device}는 누적 후 리셋하지 않아요. 실제 PLC 카운트·보존 동작은 미검증이에요.")
        node, covers = gated(node, rule.outputs, cid)
        add(node, [Output(kind="OUT", target=out) for out in rule.outputs], covers)
        done.add(cid)
        pending.remove(rule)
    if set(timers) != used_timers or set(counters) != used_counters:
        error("사용되지 않은 타이머·카운터가 있어 연결을 확정할 수 없어요.")
    if not rungs:
        error("구동할 출력 조건이 없어요.")
    covered = {cid for rung in rungs for cid in rung.covers}
    for condition in req.conditions:
        if (condition.must_pass or condition.type == "safety") and condition.id not in covered:
            error("필수·안전 조건이 회로에 실질 반영되지 않았어요.", condition.id)

    ir = Ir(rungs=rungs)
    try:
        result = validate_ir(ir, cfg, req.io_list, internal_limits=limits)
        if not result.passed:
            error("; ".join(f"{issue.code}: {issue.message}" for issue in result.errors))
        il = to_il(ir, cfg, req.io_list, internal_limits=limits)
    except IrConversionError as exc:
        error(str(exc))
    limitations.extend(w.message for w in result.warnings if w.message not in limitations)

    def describe(node: Node) -> str:
        if isinstance(node, Contact):
            row = rows.get(node.signal)
            label = f"{row.name}({node.signal})" if row else node.signal
            return f"{label} 신호값이 {'ON' if node.kind == 'NO' else 'OFF'}"
        separator = " 그리고 " if isinstance(node, Series) else " 또는 "
        return "(" + separator.join(describe(child) for child in node.items) + ")"

    explanations = []
    used_devices: set[str] = set()
    for rung in ir.rungs:
        used_devices.update(contact.signal for contact in _contacts(rung.condition))
        used_devices.update(output.target for output in rung.outputs)
        actions = []
        for output in rung.outputs:
            row = rows.get(output.target)
            label = f"{row.name}({output.target})" if row else output.target
            if output.kind == "TON":
                actions.append(f"{label} 타이머를 {output.preset_ms}ms 동안 동작시켜요")
            elif output.kind == "CTU":
                actions.append(f"{label} 카운터를 {output.preset}번까지 누적해요(리셋 없음)")
            else:
                actions.append(f"{label}를 켜고 조건이 거짓이면 꺼요")
        rung.comment = f"조건 {', '.join(rung.covers)}: {describe(rung.condition)}일 때 " + "; ".join(actions)
        explanations.append({"rung_id": rung.id, "condition_ids": rung.covers.copy(), "text": rung.comment})
    return DesignResult(
        ir=ir, io_used=[row.model_copy(deep=True) for dev, row in rows.items() if dev in used_devices],
        explanation=explanations, assumptions=req.assumptions.copy(), limitations=limitations, il=il,
    )

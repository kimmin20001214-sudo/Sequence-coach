"""자기유지 예제의 요구사항을 래더 IR로 만든다."""

from ..contracts import Contact, Ir, Output, Parallel, Rung, Series, StructuredRequirements
from ..spec import get_series, is_compatible, load_instructions
from ..validation import validate_io_list


def design_self_hold(req: StructuredRequirements) -> Ir:
    """START/STOP/MOTOR 역할을 사용한다. 일반 자연어 회로 설계는 지원하지 않는다.

    sequence 설명에는 '유지', interlock 설명에는 '꺼' 또는 'OFF'가 필요하다.
    추가 조건, 타이머, 카운터, 비상정지와 미답변 질문은 처리하지 않는다.
    내부 주소를 할당하지 않고 등록된 X/Y 주소만 사용한다.
    """
    cfg = req.plc_config
    if cfg.language != "ladder" or not is_compatible(cfg.series, cfg.cpu, cfg.language, cfg.software):
        raise ValueError("지원되는 PLC 설정의 래더만 자기유지 회로로 만들 수 있어요.")
    if req.questions or req.timers or req.counters or cfg.emergency_stop.used:
        raise ValueError("추가 질문·타이머·카운터·비상정지는 이번 자기유지 함수에서 지원하지 않아요.")

    spec = get_series(cfg.series)
    errors = validate_io_list(req.io_list, spec, spec["cpus"][cfg.cpu])
    if errors:
        raise ValueError(f"입출력 주소 오류: {errors}")
    roles = {}
    aliases = {}
    for row in req.io_list:
        name, device = row.name.strip().upper(), row.device.strip().upper()
        for alias in (name, device):
            if alias in aliases and aliases[alias] != device:
                raise ValueError(f"신호 이름 또는 주소가 중복되어 구분할 수 없어요: {alias}")
            aliases[alias] = device
        if name in roles:
            raise ValueError(f"신호 이름이 중복되어 구분할 수 없어요: {name}")
        roles[name] = row
    for role, prefix in (("START", "X"), ("STOP", "X"), ("MOTOR", "Y")):
        if role not in roles:
            raise ValueError(f"필요한 신호가 없어요: {role}")
        if not roles[role].device.strip().upper().startswith(prefix):
            raise ValueError(f"{role} 신호는 {prefix} 주소여야 해요.")

    start, stop, motor = (roles[role].device.strip().upper() for role in ("START", "STOP", "MOTOR"))
    button_kinds = {"푸시버튼 NO": "NO", "푸시버튼 NC": "NC"}
    if roles["START"].kind not in button_kinds or roles["STOP"].kind not in button_kinds:
        raise ValueError("START와 STOP은 푸시버튼 NO 또는 푸시버튼 NC로 지정해 주세요.")
    start_kind = button_kinds[roles["START"].kind]
    stop_kind = "NO" if button_kinds[roles["STOP"].kind] == "NC" else "NC"

    if len(req.conditions) != 2:
        raise ValueError("자기유지 sequence 조건과 정지 interlock 조건 하나씩만 지원해요.")
    covered = {}
    for condition in req.conditions:
        signals = set()
        for signal in condition.signals:
            alias = signal.strip().upper()
            if alias not in aliases:
                raise ValueError(f"등록되지 않은 신호예요: {signal}")
            signals.add(aliases[alias])
        if condition.type == "sequence" and signals == {start, motor} and "유지" in condition.text:
            role = "start"
        elif condition.type == "interlock" and signals == {stop, motor} and (
            "꺼" in condition.text or "OFF" in condition.text.upper()
        ):
            role = "stop"
        else:
            raise ValueError(f"지원하지 않는 자기유지 조건이에요: {condition.id}")
        if not condition.id.strip() or role in covered or condition.id in covered.values():
            raise ValueError("자기유지·정지 조건에 서로 다른 조건 번호가 필요해요.")
        covered[role] = condition.id

    needed = {"LD" if start_kind == "NO" else "LDI", "OR", "AND" if stop_kind == "NO" else "ANI", "OUT"}
    allowed = set(load_instructions()["series"].get(cfg.series, []))
    if needed - allowed:
        raise ValueError(f"허용하지 않는 명령어예요: {', '.join(sorted(needed - allowed))}")
    return Ir(rungs=[Rung(
        id="R1", comment="모터 자기유지", covers=[covered["start"], covered["stop"]],
        condition=Series(items=[
            Parallel(items=[Contact(kind=start_kind, signal=start), Contact(kind="NO", signal=motor)]),
            Contact(kind=stop_kind, signal=stop),
        ]),
        outputs=[Output(kind="OUT", target=motor)],
    )])
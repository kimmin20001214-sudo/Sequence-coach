"""손으로 쓴 시나리오와 별개로, 입력 조합을 자동으로 흔들어 보는 안전·일관성 검사.

시나리오가 부족해서 생기는 거짓 통과를 줄이려는 보강이에요. 결정적(고정 seed)이라
같은 회로는 항상 같은 결과를 내요.
"""
import random
import re
from collections.abc import Sequence

from ..contracts import Condition, Ir, VerificationIssue
from ..schemas import IoRow
from .sim import Signals, run

SCAN_MS = 10
SEQUENCES = 40
STEPS_PER_SEQUENCE = 16
MAX_DWELL_MS = 2000
STOP_WORDS = re.compile(r"정지|비상|STOP|EMG|ESTOP", re.IGNORECASE)
EMERGENCY_WORDS = re.compile(r"비상|EMG|ESTOP|E-STOP", re.IGNORECASE)
INDICATOR_WORDS = re.compile(r"램프|표시|경보|알람|부저|버저|LAMP|LED|ALARM|BUZ", re.IGNORECASE)


def _is_nc(row: IoRow) -> bool:
    return "NC" in row.kind.upper()


def _is_stop(row: IoRow) -> bool:
    return bool(STOP_WORDS.search(f"{row.name} {row.kind} {row.desc}"))


def _max_preset(ir: Ir) -> int:
    return max((o.preset_ms or 0 for r in ir.rungs for o in r.outputs if o.kind == "TON"), default=0)


def _relevant(condition: Condition, row: IoRow, dev: str) -> bool:
    keys = {s.strip().upper() for s in condition.signals}
    return bool(keys & {row.name.strip().upper(), row.device.strip().upper(), dev})


def auto_check(
    ir: Ir, io_list: Sequence[IoRow], conditions: Sequence[Condition],
) -> list[tuple[bool, VerificationIssue]]:
    """(필수 여부, 이슈) 목록을 반환한다. 필수 True면 verify에서 errors로 취급한다."""
    signals = Signals(io_list)
    inputs = [(row, signals.address(row.device)) for row in io_list if row.device.strip().upper().startswith("X")]
    outputs = [(row, signals.address(row.device)) for row in io_list if row.device.strip().upper().startswith("Y")]
    idle = {dev: 0 for _, dev in inputs}
    pressed = {dev: 1 for _, dev in inputs}
    stops = [(row, dev) for row, dev in inputs if _is_stop(row)]
    controlled = [(row, dev) for row, dev in outputs if not INDICATOR_WORDS.search(f"{row.name} {row.kind} {row.desc}")]

    def related_condition(row: IoRow, dev: str) -> str:
        return next((c.id for c in conditions if _relevant(c, row, dev)), "")

    def must_pass(row: IoRow, dev: str) -> bool:
        return any(c.must_pass and _relevant(c, row, dev) for c in conditions)

    found: list[tuple[bool, VerificationIssue]] = []
    seen: set[tuple[str, str]] = set()

    def report(required: bool, code: str, message: str, cid: str, key: str) -> None:
        if (code, key) not in seen:
            seen.add((code, key))
            found.append((required, VerificationIssue(code=code, message=message, condition_id=cid)))

    settle = _max_preset(ir) + 2 * SCAN_MS
    base = dict(idle)

    # 1) 아무것도 누르지 않았는데 출력이 켜지면 안 돼요.
    trace = run(ir, [{"t_ms": 0, "set": base}], io_list=io_list, until_ms=((settle + 99) // 100) * 100,
                scan_ms=SCAN_MS)
    for row, dev in controlled:
        if any(rec["state"].get(dev) for rec in trace):
            report(True, "AUTO_SPONTANEOUS_START",
                   f"아무 입력도 누르지 않았는데 {row.name}({dev})가 켜져요.",
                   related_condition(row, dev), dev)

    # 2) 정지·비상정지를 누른 동안은 제어 출력이 꺼져 있어야 해요.
    # 3) 어떤 입력 조합에서도 한 번도 켜지지 않는 출력은 죽은 출력이에요.
    ever_on: set[str] = set()
    movers = [dev for _, dev in inputs if all(dev != d for _, d in stops)] or [d for _, d in inputs]
    hold = settle + 200
    probes = []
    for dev in movers:
        probes.append([{"t_ms": 0, "set": dict(idle)}, {"t_ms": 10, "set": {dev: pressed[dev]}},
                       {"t_ms": 10 + hold, "set": {dev: idle[dev]}}])
    probes.append([{"t_ms": 0, "set": dict(idle)}, {"t_ms": 10, "set": {d: pressed[d] for d in movers}}])
    for probe in probes:
        end = probe[-1]["t_ms"] + hold
        for rec in run(ir, probe, io_list=io_list, until_ms=end - end % SCAN_MS, scan_ms=SCAN_MS):
            ever_on |= {d for d, v in rec["state"].items() if v}
    rng = random.Random(42)
    for _ in range(SEQUENCES):
        t = 0
        current = dict(idle)
        steps = [{"t_ms": 0, "set": dict(current)}]
        for _ in range(STEPS_PER_SEQUENCE):
            t += rng.choice([SCAN_MS, 100, 500, min(settle + 1000, MAX_DWELL_MS)]) // SCAN_MS * SCAN_MS
            pool = movers if rng.random() < 0.8 else [d for _, d in inputs]
            if not pool:
                break
            dev = rng.choice(pool)
            current[dev] = pressed[dev] if current[dev] == idle[dev] else idle[dev]
            steps.append({"t_ms": t, "set": {dev: current[dev]}})
        trace = run(ir, steps, io_list=io_list, until_ms=t + 100, scan_ms=SCAN_MS)
        for rec in trace:
            on = {d for d, v in rec["state"].items() if v}
            ever_on |= on
            for srow, sdev in stops:
                if rec["state"].get(sdev) != bool(pressed[sdev]):
                    continue
                for orow, odev in controlled:
                    if odev in on:
                        emergency = bool(EMERGENCY_WORDS.search(f"{srow.name} {srow.kind} {srow.desc}"))
                        report(emergency, "AUTO_STOP_PRIORITY",
                               f"{srow.name}({sdev})를 누른 상태인데 {orow.name}({odev})가 켜져 있어요 "
                               f"(시각 {rec['t_ms']}ms 근처의 자동 탐색).",
                               related_condition(srow, sdev) or related_condition(orow, odev),
                               f"{sdev}>{odev}")

    driven = {signals.resolve(o.target) for r in ir.rungs for o in r.outputs}
    for row, dev in controlled:
        if dev not in ever_on and dev in driven:
            report(must_pass(row, dev), "AUTO_UNREACHABLE_OUTPUT",
                   f"입력을 여러 방식으로 바꿔 봐도 {row.name}({dev})가 한 번도 켜지지 않았어요.",
                   related_condition(row, dev), dev)
    return found

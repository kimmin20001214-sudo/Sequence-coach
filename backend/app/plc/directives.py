"""분석 결과에서 design.v1 지시문을 코드로 미리 만든다(AI 출력 줄이기).

흔한 패턴만 신호 종류(kind)·조건 type·신호 배치로 확정하고, 문장에서는 "유지/동안/정지" 같은 뚜렷한
단서만 본다. 조금이라도 모호하면 만들지 않고 이유를 돌려준다. 이미 지시문이 있는 조건은 건드리지 않는다.
"""
import json
import re

from ..contracts import StructuredRequirements
from ..schemas import IoRow
from .design import PREFIX

_HOLD = re.compile(r"유지|계속\s*켜|자기\s*유지|hold", re.I)
_WHILE = re.compile(r"동안|누르고\s*있|눌려\s*있")
_STOP = re.compile(r"꺼|끄|정지|멈|차단|해제|OFF", re.I)
_PREVENT = re.compile(r"않|못|금지|막|차단")
_ANY = re.compile(r"또는|혹은|하나라도|중\s*하나|\bOR\b", re.I)
_ALL = re.compile(r"그리고|모두|동시|함께|\bAND\b", re.I)
_COUNT = re.compile(r"카운트|횟수|개수|번째|count", re.I)
_PUSH = {"푸시버튼 NO", "푸시버튼 NC"}


def _pressed(row: IoRow) -> str:
    return "off" if row.kind == "푸시버튼 NC" else "on"


def _lookup(req: StructuredRequirements) -> dict[str, IoRow]:
    rows: dict[str, IoRow] = {}
    for row in req.io_list:
        rows[row.name.strip().upper()] = row
        rows[row.device.strip().upper()] = row
    return rows


def _join(text: str, count: int) -> str | None:
    if count == 1:
        return "all"
    any_, all_ = bool(_ANY.search(text)), bool(_ALL.search(text))
    if any_ == all_:
        return None
    return "any" if any_ else "all"


def _ordered(text: str, rows: list[IoRow]) -> list[IoRow] | None:
    """문장에 나온 순서로 정렬한다. 하나라도 문장에서 못 찾으면 순서를 확정하지 않는다."""
    upper, found = text.upper(), []
    for row in rows:
        positions = [p for p in (upper.find(row.name.strip().upper()), upper.find(row.device.strip().upper())) if p >= 0]
        if not positions:
            return None
        found.append((min(positions), row))
    found.sort(key=lambda item: item[0])
    return [row for _, row in found]


def _released_off(req: StructuredRequirements, xs: list[IoRow]) -> bool:
    """분석 단계 가정에 '버튼을 떼면 꺼진다'가 해당 입력과 함께 적혀 있으면 유지가 아니라고 본다."""
    names = [r.name.upper() for r in xs]
    return any(
        re.search(r"떼면|놓으면", a) and re.search(r"꺼", a) and any(n in a.upper() for n in names)
        for a in req.assumptions if not a.startswith(PREFIX)
    )


def _one(req: StructuredRequirements, cond, lookup: dict[str, IoRow], timing_count: int) -> dict | str:
    """지시문 dict를 돌려주거나, 만들지 못한 이유(str)를 돌려준다."""
    text = cond.text
    if cond.type == "safety":
        cfg = req.plc_config.emergency_stop
        if not cfg.used:
            return "비상정지를 사용하지 않는 설정이라 safety 조건을 자동 처리하지 않아요."
        row = lookup.get(cfg.device.strip().upper())
        if row is None or [lookup.get(s.strip().upper()) for s in cond.signals] != [row]:
            return "safety 조건의 신호가 설정한 비상정지 버튼 하나와 일치하지 않아요."
        return {"condition_id": cond.id, "mode": "emergency_stop"}

    rows = []
    for signal in cond.signals:
        row = lookup.get(signal.strip().upper())
        if row is None:
            return f"{signal} 신호가 I/O 목록에 없어요."
        rows.append(row)
    xs = [r for r in rows if r.device.strip().upper().startswith("X")]
    ys = [r for r in rows if r.device.strip().upper().startswith("Y")]
    if len(xs) + len(ys) != len(rows) or not ys:
        return "입력(X)과 출력(Y)을 구분할 수 없어요."

    def inputs(items, active=None):
        return [{"signal": r.name, "active": active or _pressed(r)} for r in items]

    def base(mode: str, ins: list[IoRow], outs: list[IoRow], join: str, active=None) -> dict:
        return {"condition_id": cond.id, "mode": mode, "inputs": inputs(ins, active), "join": join,
                "outputs": [r.name for r in outs]}

    if cond.type == "sequence":
        if not xs or len(ys) < 1:
            return "시작 입력(X)이 없는 순차 조건은 동작을 확정할 수 없어요."
        join = _join(text, len(xs))
        if join is None:
            return "입력이 여럿인데 '또는/그리고' 같은 연결 단서가 없어요."
        if len(req.counters) == 1 and (_COUNT.search(text) or req.counters[0].name in text):
            result = base("count", xs, ys, join)
            result.update(counter=req.counters[0].name, reset="none")
            return result
        if _HOLD.search(text):
            return base("self_hold", xs, ys, join)
        if _WHILE.search(text) or not any(r.kind in _PUSH for r in xs) or _released_off(req, xs):
            return base("direct", xs, ys, join)
        return "버튼으로 시작하는데 '유지'인지 '누르는 동안'인지 알 수 없어요."

    if cond.type == "timing":
        if not req.timers:
            return "타이머가 없어요."
        timer = next((t for t in req.timers if t.name in text), None)
        if timer is None and len(req.timers) == 1 and timing_count == 1:
            timer = req.timers[0]
        if timer is None:
            return "어느 타이머를 쓸지 확정할 수 없어요."
        ordered = _ordered(text, rows)
        if ordered is None or len(ordered) < 2 or not ordered[-1].device.strip().upper().startswith("Y"):
            return "타이머 조건에서 입력과 출력의 순서를 확정할 수 없어요."
        ins, out = ordered[:-1], ordered[-1]
        join = _join(text, len(ins))
        if join is None:
            return "입력이 여럿인데 연결 단서가 없어요."
        result = base("on_delay", ins, [out], join, None)
        for item, row in zip(result["inputs"], ins):
            item["active"] = "on" if row.device.strip().upper().startswith("Y") else _pressed(row)
        result["timer"] = timer.name
        return result

    if cond.type == "interlock":
        if xs and _STOP.search(text):
            join = _join(text, len(xs))
            if join is None:
                return "정지 입력이 여럿인데 연결 단서가 없어요."
            return base("block", xs, ys, join)
        if not xs and len(ys) == 2 and _PREVENT.search(text):
            ordered = _ordered(text, ys)
            if ordered is None:
                return "서로 막는 출력의 방향을 확정할 수 없어요."
            return base("block", ordered[:1], ordered[1:], "all", "on")
        return "인터록이 정지인지 상호 차단인지 확정할 수 없어요."

    return f"{cond.type} 조건은 자동 지시 대상이 아니에요."


def with_auto_directives(req: StructuredRequirements) -> tuple[StructuredRequirements, dict[str, str]]:
    """지시문이 없는 조건에만 자동 지시문을 추가한 복사본과, 만들지 못한 조건의 이유를 돌려준다."""
    existing = set()
    for text in req.assumptions:
        if text.startswith(PREFIX):
            try:
                existing.add(json.loads(text[len(PREFIX):]).get("condition_id"))
            except (ValueError, AttributeError):
                pass
    lookup = _lookup(req)
    timing_count = sum(1 for c in req.conditions if c.type == "timing")
    added: list[str] = []
    skipped: dict[str, str] = {}
    for cond in req.conditions:
        if cond.id in existing:
            continue
        result = _one(req, cond, lookup, timing_count)
        if isinstance(result, str):
            skipped[cond.id] = result
        else:
            added.append(PREFIX + json.dumps(result, ensure_ascii=False))
    copy = req.model_copy(deep=True)
    copy.assumptions.extend(added)
    return copy, skipped

"""조건의 check(시험 틀) → 시험 대본(시나리오) 변환.

분석 에이전트는 틀 이름과 신호 이름만 고르고, 시각·기대값 계산은 이 코드가 한다.
모르는 신호·잘못된 값은 CheckError로 알려서 에이전트가 고치거나 백엔드가 버리게 한다.
"""
import re
from collections.abc import Callable

from ..contracts import Check, StructuredRequirements
from ..schemas import IoRow
from .sim import Signals

SCAN_MS = 10
GAP = 100  # 첫 입력까지의 대기 시간
MAX_HOLD_MS = 5000


class CheckError(ValueError):
    pass


class _Ctx:
    def __init__(self, req: StructuredRequirements):
        self.req = req
        self.signals = Signals(req.io_list)
        self.rows: dict[str, IoRow] = {self.signals.address(r.device): r for r in req.io_list}
        self.x_devs = [d for d in self.rows if d.startswith("X")]
        self.max_timer = max([t.preset_ms for t in req.timers] + [0])

    def _dev(self, name: str, kind: str, what: str) -> str:
        if not name or not name.strip():
            raise CheckError(f"{what} 신호 이름이 비어 있어요.")
        try:
            dev = self.signals.resolve(name)
        except ValueError:
            raise CheckError(f"{what} 신호 {name}가 I/O 목록에 없어요.") from None
        if dev[0] != kind:
            raise CheckError(f"{what} 신호 {name}는 {'입력(X)' if kind == 'X' else '출력(Y)'}이어야 해요.")
        return dev

    def inp(self, name: str, what: str) -> str:
        return self._dev(name, "X", what)

    def out(self, name: str, what: str) -> str:
        return self._dev(name, "Y", what)

    def trigger(self, name: str) -> str:
        """trigger가 출력(Y)이면, 그 출력을 켜는 자기유지 조건의 시작 입력으로 바꿔 쓴다."""
        try:
            dev = self.signals.resolve(name) if name and name.strip() else ""
        except ValueError:
            dev = ""
        if dev.startswith("Y"):
            for cond in self.req.conditions:
                ck = cond.check
                if ck and ck.pattern == "self_hold" and ck.start and ck.output:
                    try:
                        if self.signals.resolve(ck.output) == dev:
                            return self.inp(ck.start, "trigger")
                    except ValueError:
                        pass
        return self.inp(name, "trigger")

    def nc(self, dev: str) -> bool:
        return "NC" in self.rows[dev].kind.upper()

    def stop(self, dev: str) -> bool:
        row = self.rows[dev]
        return self.nc(dev) or bool(re.search(r"정지|비상|STOP|EMG|ESTOP", f"{row.name} {row.desc}", re.IGNORECASE))

    def idle(self, dev: str) -> int:
        return 0

    def press(self, dev: str) -> int:
        return 1

    @property
    def hold_ms(self) -> int:
        return max(300, min(self.max_timer + 300, MAX_HOLD_MS)) // SCAN_MS * SCAN_MS


class _Timeline:
    def __init__(self, ctx: _Ctx):
        self.ctx = ctx
        self.events: dict[int, dict[str, int]] = {0: {d: ctx.idle(d) for d in ctx.x_devs}}
        self.expect: list[dict] = []

    def _set(self, t: int, dev: str, value: int) -> None:
        if t % SCAN_MS:
            raise CheckError(f"시각 {t}ms는 {SCAN_MS}ms의 배수여야 해요.")
        self.events.setdefault(t, {})[dev] = value

    def press(self, t: int, *devs: str) -> None:
        for dev in devs:
            self._set(t, dev, self.ctx.press(dev))

    def release(self, t: int, *devs: str) -> None:
        for dev in devs:
            self._set(t, dev, self.ctx.idle(dev))

    def want(self, t: int, dev: str, value: int) -> None:
        self.expect.append({"t_ms": max(t, 0), "dev": dev, "value": value})

    def build(self, cid: str, **extra) -> dict:
        steps = [{"t_ms": t, "set": values} for t, values in sorted(self.events.items())]
        return {"condition_id": cid, "steps": steps, "expect": self.expect, **extra}


def _need_ms(value: int | None, field: str, minimum: int) -> int:
    if value is None or value < minimum:
        raise CheckError(f"{field}는 {minimum}ms 이상의 정수여야 해요.")
    if value % SCAN_MS:
        raise CheckError(f"{field}는 {SCAN_MS}ms의 배수여야 해요.")
    return value


def _self_hold(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    start, stop = ctx.inp(c.start, "start"), ctx.inp(c.stop, "stop")
    out = ctx.out(c.output, "output")
    t1 = _Timeline(ctx)
    t1.press(GAP, start)
    t1.release(GAP + 50, start)
    t1.want(GAP - 10, out, 0)
    t1.want(GAP + 100, out, 1)
    t1.want(GAP + 500, out, 1)

    t2 = _Timeline(ctx)
    t2.press(GAP, start)
    t2.release(GAP + 50, start)
    t2.want(GAP + 400, out, 1)
    t2.press(GAP + 500, stop)
    t2.want(GAP + 600, out, 0)
    t2.release(GAP + 700, stop)
    t2.want(GAP + 900, out, 0)

    t3 = _Timeline(ctx)
    t3.press(GAP, stop)
    t3.press(GAP + 100, start)
    t3.release(GAP + 150, start)
    t3.want(GAP + 200, out, 0)
    t3.want(GAP + 400, out, 0)
    return [t.build(cid) for t in (t1, t2, t3)]


def _stop_priority(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    stop = ctx.inp(c.stop, "stop")
    outs = [ctx.out(o, "output") for o in c.outputs]
    if not outs:
        raise CheckError("outputs에 꺼져야 할 출력이 하나 이상 필요해요.")
    others = [d for d in ctx.x_devs if d != stop]
    hold = ctx.hold_ms
    tl = _Timeline(ctx)
    tl.press(0, stop)
    tl.press(GAP, *others)
    for out in outs:
        for t in (GAP + 50, GAP + 300, GAP + hold):
            tl.want(t, out, 0)
    return [tl.build(cid)]


def _on_delay(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    trig, out = ctx.trigger(c.trigger), ctx.out(c.output, "output")
    delay = _need_ms(c.delay_ms, "delay_ms", 100)
    on_at = GAP + delay
    t1 = _Timeline(ctx)
    t1.press(GAP, trig)
    t1.want(GAP - 10, out, 0)
    t1.want(GAP + delay // 2 // SCAN_MS * SCAN_MS, out, 0)
    t1.want(on_at - 30, out, 0)
    t1.want(on_at + 30, out, 1)
    t1.want(on_at + 300, out, 1)
    result = [t1.build(cid)]
    if c.stop.strip():
        stop = ctx.inp(c.stop, "stop")
        t2 = _Timeline(ctx)
        t2.press(GAP, trig)
        t2.want(on_at + 100, out, 1)
        t2.press(on_at + 200, stop)
        t2.want(on_at + 300, out, 0)
        result.append(t2.build(cid))
    return result


def _timed_on(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    trig, out = ctx.trigger(c.trigger), ctx.out(c.output, "output")
    dur = _need_ms(c.duration_ms, "duration_ms", 200)
    tl = _Timeline(ctx)
    tl.press(GAP, trig)
    tl.release(GAP + 50, trig)
    tl.want(GAP - 10, out, 0)
    tl.want(GAP + 40, out, 1)
    tl.want(GAP + dur - 50, out, 1)
    tl.want(GAP + dur + 50, out, 0)
    tl.want(GAP + dur + 300, out, 0)
    return [tl.build(cid)]


def _sweep(ctx: _Ctx, exclude: set[str]) -> tuple[_Timeline, int]:
    """정지·비상정지 입력을 뺀 입력을 하나씩·둘씩·전부·차례로 눌러 보는 입력 탐색."""
    xs = [d for d in ctx.x_devs if not ctx.stop(d) and d not in exclude][:8]
    hold = ctx.hold_ms
    groups = [[x] for x in xs]
    if len(xs) <= 4 or hold <= 1000:
        groups += [[a, b] for i, a in enumerate(xs) for b in xs[i + 1:]]
    groups.append(xs)
    tl = _Timeline(ctx)
    t = GAP
    for group in groups:
        if not group:
            continue
        tl.press(t, *group)
        t += hold
        tl.release(t, *group)
        t += hold
    for i, x in enumerate(xs):  # 차례로 누르고 있다가 한꺼번에 뗀다
        tl.press(t + i * hold, x)
    t += len(xs) * hold
    tl.release(t, *xs)
    t += hold
    tl.release(t, *xs)
    return tl, t


def _interlock(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    a, b = ctx.out(c.a, "a"), ctx.out(c.b, "b")
    if a == b:
        raise CheckError("인터록의 a와 b는 서로 다른 출력이어야 해요.")
    tl, _ = _sweep(ctx, set())
    return [tl.build(cid, exclusive=[[a, b]])]


def _indicator(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    out, lamp = ctx.out(c.output, "output"), ctx.out(c.lamp, "lamp")
    tl, _ = _sweep(ctx, set())
    return [tl.build(cid, follow=[[out, lamp]])]


def _inputs(ctx: _Ctx, c: Check) -> list[str]:
    devs = [ctx.inp(n, "inputs") for n in c.inputs]
    if len(devs) < 2 or len(set(devs)) != len(devs):
        raise CheckError("inputs에는 서로 다른 입력이 두 개 이상 필요해요.")
    return devs


def _and_enable(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    ins, out = _inputs(ctx, c), ctx.out(c.output, "output")
    tl = _Timeline(ctx)
    tl.press(GAP, *ins)
    tl.want(GAP - 10, out, 0)
    tl.want(GAP + 200, out, 1)
    tl.want(GAP + 400, out, 1)
    result = [tl.build(cid)]
    for missing in ins:
        part = _Timeline(ctx)
        part.press(GAP, *[d for d in ins if d != missing])
        part.want(GAP + 200, out, 0)
        part.want(GAP + 400, out, 0)
        result.append(part.build(cid))
    return result


def _or_enable(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    ins, out = _inputs(ctx, c), ctx.out(c.output, "output")
    none = _Timeline(ctx)
    none.want(GAP + 100, out, 0)
    result = [none.build(cid)]
    for dev in ins:
        tl = _Timeline(ctx)
        tl.press(GAP, dev)
        tl.want(GAP + 200, out, 1)
        tl.want(GAP + 400, out, 1)
        result.append(tl.build(cid))
    return result


def _set_reset(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    st, rst = ctx.inp(c.set_input, "set_input"), ctx.inp(c.reset_input, "reset_input")
    out = ctx.out(c.output, "output")
    t1 = _Timeline(ctx)
    t1.want(GAP - 10, out, 0)
    t1.press(GAP, st)
    t1.release(GAP + 50, st)
    t1.want(GAP + 100, out, 1)
    t1.want(GAP + 300, out, 1)
    t1.press(GAP + 400, rst)
    t1.release(GAP + 450, rst)
    t1.want(GAP + 500, out, 0)
    t1.want(GAP + 700, out, 0)
    t2 = _Timeline(ctx)
    t2.press(GAP, rst)
    t2.release(GAP + 50, rst)
    t2.want(GAP + 200, out, 0)
    return [t1.build(cid), t2.build(cid)]


def _custom(ctx: _Ctx, cid: str, c: Check) -> list[dict]:
    if not c.steps or not c.expect:
        raise CheckError("custom에는 steps와 expect가 모두 필요해요.")
    return [{"condition_id": cid, "steps": c.steps, "expect": c.expect}]


GENERATORS: dict[str, Callable[[_Ctx, str, Check], list[dict]]] = {
    "self_hold": _self_hold, "stop_priority": _stop_priority, "on_delay": _on_delay,
    "timed_on": _timed_on, "interlock": _interlock, "and_enable": _and_enable,
    "or_enable": _or_enable, "indicator": _indicator, "set_reset": _set_reset, "custom": _custom,
}


def scenarios_for(req: StructuredRequirements, condition_id: str, check: Check) -> list[dict]:
    return GENERATORS[check.pattern](_Ctx(req), condition_id, check)


def build_scenarios(req: StructuredRequirements) -> tuple[list[dict], list[tuple[str, str]]]:
    """모든 조건의 대본과 (조건 ID, 오류 문장) 목록을 반환한다."""
    scenarios: list[dict] = []
    problems: list[tuple[str, str]] = []
    try:
        ctx = _Ctx(req)
    except ValueError as exc:
        return [], [(c.id, f"I/O 목록 오류로 시험 대본을 만들 수 없어요: {exc}") for c in req.conditions if c.check]
    for condition in req.conditions:
        if condition.check is None:
            continue
        try:
            scenarios.extend(GENERATORS[condition.check.pattern](ctx, condition.id, condition.check))
        except CheckError as exc:
            problems.append((condition.id, f"조건 {condition.id}의 시험 틀({condition.check.pattern})이 올바르지 않아요: {exc}"))
    return scenarios, problems

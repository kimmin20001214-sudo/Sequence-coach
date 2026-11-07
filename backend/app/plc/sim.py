"""실제 PLC에 연결하지 않는 결정적 스캔 모의 실행."""
import re
from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from ..contracts import Contact, Ir, Node
from ..schemas import IoRow

MAX_SCANS = 100_000


Bit = StrictBool | Annotated[StrictInt, Field(ge=0, le=1)]


class InputStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: StrictInt = Field(ge=0)
    set: dict[str, Bit]


class Signals:
    """Q 주소와 등록 I/O 이름을 같은 주소로 읽는다. 원본 데이터는 변경하지 않는다."""

    def __init__(self, io_list: Sequence[IoRow]):
        self.aliases: dict[str, str] = {}
        self.devices: set[str] = set()
        for row in io_list:
            dev = self.address(row.device)
            if dev is None or dev[0] not in "XY":
                raise ValueError(f"{row.device}: 등록 I/O는 Q시리즈 X/Y 주소여야 해요.")
            if dev in self.devices:
                raise ValueError(f"{dev}: 등록 I/O 주소가 중복돼요.")
            self.devices.add(dev)
            for token in (row.device.strip().upper(), row.name.strip().upper()):
                direct = self.address(token)
                if not token or (direct and direct != dev) or (
                    token in self.aliases and self.aliases[token] != dev
                ):
                    raise ValueError(f"{token}: 신호 이름이 비어 있거나 모호해요.")
                self.aliases[token] = dev

    @staticmethod
    def address(text: str) -> str | None:
        token = text.strip().upper()
        if re.fullmatch(r"[XY][0-9A-F]+", token):
            return token[0] + format(int(token[1:], 16), "X")
        if re.fullmatch(r"[MTC][0-9]+", token):
            return token[0] + str(int(token[1:]))
        return None

    def resolve(self, text: str) -> str:
        dev = self.aliases.get(text.strip().upper()) or self.address(text)
        if dev is None or (dev[0] in "XY" and dev not in self.devices):
            raise ValueError(f"{text}: 모의 실행에서 읽을 수 없는 신호예요.")
        return dev


def run(
    ir: Ir,
    steps: list[dict],
    *,
    io_list: Sequence[IoRow],
    scan_ms: int = 10,
    until_ms: int | None = None,
) -> list[dict]:
    """입력 반영 후 렁을 순서대로 실행한 매 스캔의 상태를 반환한다.

    앞 렁의 출력은 같은 스캔의 다음 렁에서 읽는다. 최초 TON ON은
    경과 0ms이며 이후 참인 스캔마다 시간을 누적한다. CTU는 상승 에지만 센다.
    """
    if type(scan_ms) is not int or scan_ms <= 0:
        raise ValueError("스캔 간격은 양의 정수 ms여야 해요.")
    events = [InputStep.model_validate(step) for step in steps]
    end = (events[-1].t_ms if events else 0) if until_ms is None else until_ms
    if type(end) is not int or end < 0 or end % scan_ms:
        raise ValueError("종료 시각은 0 이상의 스캔 간격 배수여야 해요.")
    if end // scan_ms + 1 > MAX_SCANS:
        raise ValueError(f"시나리오 하나는 최대 {MAX_SCANS} 스캔까지 실행해요.")

    signals = Signals(io_list)
    normalized_events: dict[int, dict[str, bool]] = {}
    previous = -1
    for event in events:
        if event.t_ms <= previous or event.t_ms % scan_ms or event.t_ms > end:
            raise ValueError("입력 시각은 중복 없는 오름차순 스캔 시각이며 종료 이내여야 해요.")
        previous = event.t_ms
        values: dict[str, bool] = {}
        for token, value in event.set.items():
            dev = signals.resolve(token)
            if dev[0] != "X" or value not in (0, 1):
                raise ValueError("입력 시퀀스는 등록 X 신호의 0/1만 변경할 수 있어요.")
            if dev in values:
                raise ValueError(f"{dev}: 같은 시각에 이름과 주소로 중복 입력했어요.")
            values[dev] = bool(value)
        normalized_events[event.t_ms] = values

    resolved = ir.model_copy(deep=True)
    state = {dev: False for dev in signals.devices}

    def normalize(node: Node) -> None:
        if isinstance(node, Contact):
            node.signal = signals.resolve(node.signal)
            state.setdefault(node.signal, False)
        else:
            for child in node.items:
                normalize(child)

    timers: dict[str, int] = {}
    counters: dict[str, int] = {}
    for rung in resolved.rungs:
        normalize(rung.condition)
        for output in rung.outputs:
            output.target = signals.resolve(output.target)
            allowed = {"TON": "T", "CTU": "C"}.get(output.kind, "YM")
            if output.target[0] not in allowed:
                raise ValueError(f"{output.kind} 출력에 {output.target}를 사용할 수 없어요.")
            if output.kind == "TON":
                if output.preset_ms is None or output.preset_ms <= 0:
                    raise ValueError("TON 설정시간은 양의 정수 ms여야 해요.")
                timers[output.target] = 0
            if output.kind == "CTU":
                if output.preset is None or output.preset <= 0:
                    raise ValueError("CTU 설정값은 양의 정수여야 해요.")
                counters[output.target] = 0
            state.setdefault(output.target, False)

    def evaluate(node: Node) -> bool:
        if isinstance(node, Contact):
            value = state[node.signal]
            return value if node.kind == "NO" else not value
        values = [evaluate(child) for child in node.items]
        return all(values) if node.type == "AND" else any(values)

    active_timers: set[str] = set()
    counter_inputs: dict[str, bool] = {}
    trace = []
    for t_ms in range(0, end + 1, scan_ms):
        state.update(normalized_events.get(t_ms, {}))
        for rung in resolved.rungs:
            enabled = evaluate(rung.condition)
            for output in rung.outputs:
                dev = output.target
                if output.kind == "OUT":
                    state[dev] = enabled
                elif output.kind == "SET":
                    if enabled:
                        state[dev] = True
                elif output.kind == "RST":
                    if enabled:
                        state[dev] = False
                elif output.kind == "TON":
                    assert output.preset_ms is not None
                    if enabled:
                        timers[dev] = timers[dev] + scan_ms if dev in active_timers else 0
                        active_timers.add(dev)
                    else:
                        timers[dev] = 0
                        active_timers.discard(dev)
                    state[dev] = enabled and timers[dev] >= output.preset_ms
                elif output.kind == "CTU":
                    assert output.preset is not None
                    if enabled and not counter_inputs.get(dev, False):
                        counters[dev] += 1
                    counter_inputs[dev] = enabled
                    state[dev] = counters[dev] >= output.preset
                else:
                    raise ValueError(f"지원하지 않는 출력 명령: {output.kind}")
        trace.append({
            "t_ms": t_ms, "state": state.copy(),
            "timers": timers.copy(), "counters": counters.copy(),
        })
    return trace

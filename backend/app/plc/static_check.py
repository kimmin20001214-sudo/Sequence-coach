"""기존 rules.py에 없는 이중 출력 검사만 보강한다."""
from collections.abc import Sequence

from ..contracts import Ir, VerificationIssue
from ..schemas import IoRow
from .sim import Signals


def check_double_outputs(ir: Ir, io_list: Sequence[IoRow]) -> list[VerificationIssue]:
    """사전 규칙 검사를 통과한 IR을 검사한다. SET/RST 쌍은 허용한다."""
    signals = Signals(io_list)
    seen: dict[str, str] = {}
    errors = []
    for rung in ir.rungs:
        for output in rung.outputs:
            if output.kind not in {"OUT", "TON", "CTU"}:
                continue
            dev = signals.resolve(output.target)
            if dev in seen:
                errors.append(VerificationIssue(
                    code="DOUBLE_COIL",
                    message=f"{dev} 출력이 렁 {seen[dev]}와 {rung.id}에서 중복돼요.",
                    rung_id=rung.id,
                ))
            else:
                seen[dev] = rung.id
    return errors

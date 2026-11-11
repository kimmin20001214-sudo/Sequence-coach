"""IR → GX Works 가져오기용 명령어(IL) 텍스트 변환.

실제 GX Works에서 가져오기·컴파일을 확인하기 전(docs/poc-gxworks.md)이라 결과는 항상 `unverified`다.
호환 파일이라고 단정하지 않는다.
"""
from dataclasses import dataclass
from typing import Literal

from ..contracts import Contact, Ir, Node, Output, Series

CompatibilityStatus = Literal["verified", "unverified", "unsupported", "failed"]
TIMER_UNIT_MS = 100


class ExportError(ValueError):
    pass


@dataclass
class ExportResult:
    status: CompatibilityStatus
    format: str
    content: str
    notes: list[str]


def _device(signal: str, names: dict[str, str]) -> str:
    return names.get(signal, signal).upper()


def _contact(c: Contact, op: str, names: dict[str, str]) -> str:
    mnemonic = {"LD": ("LD", "LDI"), "AND": ("AND", "ANI"), "OR": ("OR", "ORI")}[op]
    return f"{mnemonic[0 if c.kind == 'NO' else 1]} {_device(c.signal, names)}"


def _emit(node: Node, names: dict[str, str]) -> list[str]:
    if isinstance(node, Contact):
        return [_contact(node, "LD", names)]
    join, block = ("AND", "ANB") if isinstance(node, Series) else ("OR", "ORB")
    lines = _emit(node.items[0], names)
    for item in node.items[1:]:
        if isinstance(item, Contact):
            lines.append(_contact(item, join, names))
        else:
            lines += _emit(item, names) + [block]
    return lines


def _output(o: Output, names: dict[str, str]) -> str:
    target = _device(o.target, names)
    if o.kind == "TON":
        if o.preset_ms % TIMER_UNIT_MS:
            raise ExportError(f"{o.target}: 타이머 설정 시간은 {TIMER_UNIT_MS}ms의 배수여야 해요.")
        return f"OUT {target} K{o.preset_ms // TIMER_UNIT_MS}"
    if o.kind == "CTU":
        return f"OUT {target} K{o.preset}"
    return f"{o.kind} {target}"


def ir_to_il(ir: Ir, names: dict[str, str] | None = None) -> ExportResult:
    """names는 I/O 이름 → 디바이스 주소(START → X1) 대응표다."""
    names = names or {}
    lines: list[str] = []
    for rung in ir.rungs:
        lines.append(f"; {rung.id} {rung.comment}".rstrip())
        lines += _emit(rung.condition, names)
        lines += [_output(o, names) for o in rung.outputs]
    lines.append("END")
    return ExportResult(
        status="unverified",
        format="il-text",
        content="\n".join(lines) + "\n",
        notes=["GX Works 가져오기·컴파일을 확인하지 않았어요.", "설계 초안이며 실제 설비 적용 전 사람의 검토가 필요해요."],
    )

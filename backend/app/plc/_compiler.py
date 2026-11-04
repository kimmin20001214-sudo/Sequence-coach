"""규칙 검사를 통과한 Q 래더 IR의 내부 변환기."""
from ..contracts import Contact, Ir, Node
from ..schemas import PlcConfig


def _condition(node: Node) -> list[str]:
    if isinstance(node, Contact):
        return [f"{'LD' if node.kind == 'NO' else 'LDI'} {node.signal}"]

    lines = _condition(node.items[0])
    for item in node.items[1:]:
        if isinstance(item, Contact):
            op = ("AND" if item.kind == "NO" else "ANI") if node.type == "AND" else (
                "OR" if item.kind == "NO" else "ORI"
            )
            lines.append(f"{op} {item.signal}")
        else:
            lines.extend(_condition(item))
            lines.append("ANB" if node.type == "AND" else "ORB")
    return lines


def compile_ir(ir: Ir, config: PlcConfig) -> list[tuple[str, str]]:
    """허용목록 검사 키와 표시할 명령어를 함께 만든다. 공개 호출은 to_il을 쓴다."""
    instructions: list[tuple[str, str]] = []
    for rung in ir.rungs:
        instructions.extend((line.split()[0], line) for line in _condition(rung.condition))
        if len(rung.outputs) > 1:
            instructions.append(("MPS", "MPS"))
        for index, output in enumerate(rung.outputs):
            if index:
                op = "MPP" if index == len(rung.outputs) - 1 else "MRD"
                instructions.append((op, op))
            if output.kind == "TON":
                assert output.preset_ms is not None
                line = f"OUT {output.target} K{output.preset_ms // config.timer_unit_ms}"
                instructions.append(("OUT T", line))
            elif output.kind == "CTU":
                line = f"OUT {output.target} K{output.preset}"
                instructions.append(("OUT C", line))
            else:
                instructions.append((output.kind, f"{output.kind} {output.target}"))
    instructions.append(("END", "END"))
    return instructions

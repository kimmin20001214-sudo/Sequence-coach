"""렁과 접점·출력을 비교한다. 설명/covers만 바꾼 것은 회로 수정이 아니다."""
from collections import Counter

from ..contracts import Contact, Ir, Node, Rung


def _contacts(node: Node) -> Counter[tuple[str, str]]:
    if isinstance(node, Contact):
        return Counter({(node.signal, node.kind): 1})
    return sum((_contacts(child) for child in node.items), Counter())


def _circuit(rung: Rung) -> dict:
    return {"id": rung.id, "condition": rung.condition.model_dump(),
            "outputs": [o.model_dump() for o in rung.outputs]}


def _summary(old: Rung, new: Rung, moved: bool) -> str:
    parts = []
    before, after = _contacts(old.condition), _contacts(new.condition)
    for label, contacts in (("접점 삭제", before - after), ("접점 추가", after - before)):
        for (signal, kind), count in contacts.items():
            parts.append(f"{signal} {kind} {label}" + (f" {count}개" if count > 1 else ""))
    if old.condition != new.condition:
        parts.append("접점 연결 논리·순서 변경")
    for first, second in zip(old.outputs, new.outputs):
        if first.target != second.target:
            parts.append(f"출력 대상 {first.target}→{second.target}")
        if first.kind != second.kind:
            parts.append(f"{second.target} 출력 종류 {first.kind}→{second.kind}")
        if first.preset_ms != second.preset_ms:
            parts.append(f"{second.target} 설정시간 {first.preset_ms}→{second.preset_ms}ms")
        if first.preset != second.preset:
            parts.append(f"{second.target} 카운터 설정값 {first.preset}→{second.preset}")
    for output in old.outputs[len(new.outputs):]:
        parts.append(f"출력 삭제 {output.target} {output.kind}")
    for output in new.outputs[len(old.outputs):]:
        parts.append(f"출력 추가 {output.target} {output.kind}")
    if moved:
        parts.append("렁 실행 순서 변경")
    return "; ".join(parts)


def diff_ir(old: Ir, new: Ir) -> dict:
    """원본을 변경하지 않으며, 실행 순서와 AND/OR 구조도 비교한다."""
    before = {r.id: r for r in old.rungs}
    after = {r.id: r for r in new.rungs}
    if len(before) != len(old.rungs) or len(after) != len(new.rungs):
        raise ValueError("렁 ID는 고유해야 해요.")
    old_order = [r.id for r in old.rungs if r.id in after]
    new_order = [r.id for r in new.rungs if r.id in before]
    positions = {rid: i for i, rid in enumerate(old_order)}
    changed = []
    for i, rid in enumerate(new_order):
        moved = positions[rid] != i
        if _circuit(before[rid]) != _circuit(after[rid]) or moved:
            changed.append({"rung_id": rid, "summary": _summary(before[rid], after[rid], moved)})
    added = [r.id for r in new.rungs if r.id not in before]
    removed = [r.id for r in old.rungs if r.id not in after]
    return {"added": added, "removed": removed, "changed": changed,
            "same": not (added or removed or changed)}

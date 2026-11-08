import json
from pathlib import Path

import pytest

from app.contracts import Ir
from app.plc.ir_diff import diff_ir


def timer_ir():
    case = json.loads((Path(__file__).parent / "fixtures/on_delay.json").read_text(encoding="utf-8"))
    return Ir.model_validate(case["ir"])


def test_same_circuit_and_timer_change():
    old = timer_ir()
    assert diff_ir(old, old.model_copy(deep=True)) == {
        "added": [], "removed": [], "changed": [], "same": True,
    }
    new = old.model_copy(deep=True)
    timer = next(o for r in new.rungs for o in r.outputs if o.kind == "TON")
    timer.preset_ms = 5000
    change = diff_ir(old, new)
    assert not change["same"]
    assert any("T0" in c["summary"] and "3000→5000ms" in c["summary"] for c in change["changed"])
    assert old != new


def test_contacts_outputs_and_rung_changes():
    old = timer_ir()
    new = old.model_copy(deep=True)
    payload = new.model_dump()
    payload["rungs"][0]["condition"] = {"type": "AND", "items": [
        payload["rungs"][0]["condition"],
        {"type": "contact", "kind": "NC", "signal": "M1"},
    ]}
    payload["rungs"][0]["outputs"][0]["target"] = "T1"
    new = Ir.model_validate(payload)
    summary = diff_ir(old, new)["changed"][0]["summary"]
    assert "접점 추가" in summary and "M1" in summary
    assert "출력 대상" in summary and f"{old.rungs[0].outputs[0].target}→T1" in summary
    assert "접점 삭제" in diff_ir(new, old)["changed"][0]["summary"]
    added = old.model_copy(deep=True)
    rung = added.rungs[0].model_copy(deep=True)
    rung.id = "R9"
    added.rungs.append(rung)
    assert diff_ir(old, added)["added"] == ["R9"]
    assert diff_ir(added, old)["removed"] == ["R9"]


def test_order_and_logic_changes_but_annotations_are_not_repairs():
    old = timer_ir()
    new = old.model_copy(deep=True)
    new.rungs[0].comment = "고쳤어요"
    new.rungs[0].covers = ["C99"]
    assert diff_ir(old, new)["same"]
    new.rungs.reverse()
    assert not diff_ir(old, new)["same"]
    assert any("순서" in c["summary"] for c in diff_ir(old, new)["changed"])
    new = old.model_copy(deep=True)
    node = new.rungs[0].condition.model_dump()
    new.rungs[0].condition = Ir.model_validate({
        "rungs": [{"id": "R", "condition": {"type": "OR", "items": [node, node]},
                   "outputs": [{"kind": "OUT", "target": "M0"}]}],
    }).rungs[0].condition
    assert "논리" in diff_ir(old, new)["changed"][0]["summary"]


def test_duplicate_rung_ids_are_rejected():
    old = timer_ir()
    old.rungs.append(old.rungs[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="고유"):
        diff_ir(old, old)

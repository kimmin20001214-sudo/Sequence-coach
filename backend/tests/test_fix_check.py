import json
from pathlib import Path

import pytest

from app.contracts import Check, Ir, Rung, StructuredRequirements
from app.plc.fix_check import check_fix
from app.plc.verify import verify_with_checks


def interlock_pair():
    """기존 예시에 역방향 회로와 시험 틀을 보강한 뒤 인터록 접점을 제거한다."""
    case = json.loads((Path(__file__).parent / "fixtures/estop_interlock.json").read_text(encoding="utf-8"))
    req = StructuredRequirements.model_validate(case["requirements"])
    req.io_list.append(req.io_list[1].model_copy(update={"device": "X3", "name": "REV_START"}))
    req.conditions[0].check = Check(pattern="self_hold", start="START", stop="STOP", output="MOTOR_FWD")
    req.conditions[1].check = Check(pattern="interlock", a="MOTOR_FWD", b="MOTOR_REV")
    req.conditions[2].check = Check(pattern="stop_priority", stop="EMG", outputs=["MOTOR_FWD", "MOTOR_REV"])
    fixed = Ir.model_validate(case["ir"])
    fixed.rungs.append(Rung(
        id="R2", covers=["C2", "C3"], condition={
            "type": "AND", "items": [
                {"type": "contact", "kind": "NO", "signal": "X0"},
                {"type": "contact", "kind": "NO", "signal": "X2"},
                {"type": "contact", "kind": "NO", "signal": "X3"},
                {"type": "contact", "kind": "NC", "signal": "Y0"},
            ],
        }, outputs=[{"kind": "OUT", "target": "Y1"}],
    ))
    broken = fixed.model_copy(deep=True)
    broken.rungs[1].condition.items.pop()
    return req, broken, fixed


def test_broken_interlock_repaired_by_person_passes_real_verification():
    req, broken, fixed = interlock_pair()
    before = verify_with_checks(req, broken)
    assert not before.passed and any(e.condition_id == "C2" for e in before.errors)
    checked = check_fix(req, broken, fixed, before)
    assert checked.ok and checked.result.passed and not checked.regressions
    assert "모의" in checked.reason and "접점 추가" in checked.reason
    assert broken.rungs[1].condition != fixed.rungs[1].condition


def test_continued_failure_and_no_change_are_rejected():
    req, broken, fixed = interlock_pair()
    before = verify_with_checks(req, broken)
    assert not check_fix(req, broken, broken, before).ok
    still_bad = broken.model_copy(deep=True)
    still_bad.rungs[0].condition.items.pop()
    checked = check_fix(req, broken, still_bad, before)
    assert not checked.ok and checked.result and not checked.result.passed
    assert "실패" in checked.reason or "통과하지" in checked.reason


@pytest.mark.parametrize("required", [True, False])
def test_regression_of_previously_passed_condition_is_rejected(required):
    req, broken, fixed = interlock_pair()
    req.conditions[0].must_pass = required
    before = verify_with_checks(req, broken)
    assert any(w.code == "CONDITION_PASSED" and w.condition_id == "C1" for w in before.warnings)
    fixed.rungs[0].condition.items.pop(2)  # 정지 접점 제거
    checked = check_fix(req, broken, fixed, before)
    assert not checked.ok and "C1" in checked.regressions and "퇴보" in checked.reason


@pytest.mark.parametrize("payload", [
    {"rungs": []},
    {"rungs": [{"id": "R1"}]},
])
def test_bad_ir_format_is_rejected(payload):
    req, broken, _ = interlock_pair()
    checked = check_fix(req, broken, payload, verify_with_checks(req, broken))
    assert not checked.ok and "형식" in checked.reason and checked.result is None


def test_design_errors_are_rejected_before_simulation():
    req, broken, fixed = interlock_pair()
    fixed.rungs[0].condition.items.pop(0)
    checked = check_fix(req, broken, fixed.model_dump(), verify_with_checks(req, broken))
    assert not checked.ok and "비상정지" in checked.reason and checked.result is None


def test_missing_required_check_cannot_pass():
    req, broken, fixed = interlock_pair()
    req.conditions[1].check = None
    checked = check_fix(req, broken, fixed, verify_with_checks(req, broken))
    assert not checked.ok and checked.result and not checked.result.passed


def test_mutated_ir_model_is_revalidated():
    req, broken, fixed = interlock_pair()
    fixed.rungs[0].outputs[0].kind = "INVALID"
    checked = check_fix(req, broken, fixed, verify_with_checks(req, broken))
    assert not checked.ok and "형식" in checked.reason

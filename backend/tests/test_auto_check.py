"""시나리오 없이도 동작하는 자동 안전 탐색."""
import pytest

from app.plc.auto_check import auto_check
from app.plc.verify import verify
from test_scenarios import SCENARIO_NAMES, load_scenarios


def _codes(found):
    return {(required, issue.code) for required, issue in found}


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_normal_circuits_have_no_auto_findings(name):
    req, ir, _ = load_scenarios(name)
    assert auto_check(ir, req.io_list, req.conditions) == []


def test_missing_stop_contact_is_found_without_any_scenario():
    req, ir, _ = load_scenarios("self_hold")
    ir.rungs[0].condition = ir.rungs[0].condition.items[0]
    found = auto_check(ir, req.io_list, req.conditions)
    assert any(issue.code == "AUTO_STOP_PRIORITY" for _, issue in found)
    result = verify(req, ir, [])
    assert not result.passed


def _strip(node, signals):
    if hasattr(node, "items"):
        node.items = [_strip(i, signals) for i in node.items if getattr(i, "signal", None) not in signals]
    return node


def test_missing_emergency_stop_is_a_required_failure():
    req, ir, _ = load_scenarios("estop_interlock")
    emg = {r.name for r in req.io_list if "EMG" in r.name.upper()} | {
        r.device for r in req.io_list if "EMG" in r.name.upper()}
    for rung in ir.rungs:
        rung.condition = _strip(rung.condition, emg)
    found = auto_check(ir, req.io_list, req.conditions)
    assert any(required and issue.code == "AUTO_STOP_PRIORITY" for required, issue in found)


def test_dead_output_is_reported():
    req, ir, _ = load_scenarios("self_hold")
    ir.rungs[0].outputs[0].kind = "RST"
    found = auto_check(ir, req.io_list, req.conditions)
    assert any(issue.code == "AUTO_UNREACHABLE_OUTPUT" for _, issue in found)


def test_coverage_gap_is_warned_when_scenario_skips_a_signal():
    req, ir, scenarios = load_scenarios("self_hold")
    only_c2 = [s for s in scenarios if s.get("condition_id") == "C2"]
    for s in only_c2:
        for step in s["steps"]:
            step["set"].pop("STOP", None)
            step["set"].pop("X2", None)
    result = verify(req, ir, only_c2)
    assert any(w.code == "COVERAGE_GAP" for w in result.warnings)

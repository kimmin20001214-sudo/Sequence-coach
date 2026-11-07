"""공통 계약을 바꾸지 않는 코드 기반 회로 판정."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.contracts import VerificationResult
from app.plc.verify import verify
from test_scenarios import SCENARIO_NAMES, load_scenarios


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_normal_circuits_pass(name):
    req, ir, scenarios = load_scenarios(name)
    result = verify(req, ir, scenarios)
    assert isinstance(result, VerificationResult)
    assert result.passed and not result.errors
    assert any("안전을 보장하지" in issue.message for issue in result.warnings)
    assert any(issue.code == "UNVERIFIED_CPU_LIMITS" for issue in result.warnings)


def test_missing_nc_interlock_reports_condition_rung_expected_actual_and_time():
    req, ir, scenarios = load_scenarios("estop_interlock")
    ir.rungs[1].condition.items = [
        item for item in ir.rungs[1].condition.items if getattr(item, "kind", None) != "NC"
    ]
    result = verify(req, ir, scenarios)
    assert not result.passed
    failure = next(issue for issue in result.errors
                   if issue.code == "UNMET_CONDITION" and issue.condition_id == "C2")
    assert failure.rung_id == "R2"
    assert all(text in failure.message for text in ("기대값 0", "실제값 1", "100ms", "Y1"))


def test_missing_stop_contact_fails_after_motor_was_running():
    req, ir, scenarios = load_scenarios("self_hold")
    ir.rungs[0].condition = ir.rungs[0].condition.items[0]
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert any(issue.condition_id == "C2" and "100ms" in issue.message for issue in result.errors)


def test_missing_timer_fails_instead_of_passing_on_input_validation():
    req, ir, scenarios = load_scenarios("on_delay_5s")
    ir.rungs.pop(1)
    ir.rungs[1].condition.signal = "Y0"
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert any(issue.code == "UNMET_CONDITION" and issue.condition_id == "C2"
               and "기대값 0" in issue.message and "실제값 1" in issue.message
               for issue in result.errors)


def test_required_condition_without_scenario_is_unverifiable():
    req, ir, scenarios = load_scenarios("self_hold")
    result = verify(req, ir, scenarios[:1])
    assert not result.passed
    assert any(issue.code == "UNVERIFIABLE" and issue.condition_id == "C2" for issue in result.errors)


@pytest.mark.parametrize("kind", ["missing", "fail", "invalid", "pass"])
def test_optional_condition_result_is_recorded_only_in_warnings(kind):
    req, ir, scenarios = load_scenarios("self_hold")
    req.conditions[1].must_pass = False
    if kind == "missing":
        scenarios.pop()
    elif kind == "fail":
        scenarios[1]["expect"][0]["value"] = 0
    elif kind == "invalid":
        scenarios[1]["expect"] = []
    result = verify(req, ir, scenarios)
    assert result.passed and not result.errors
    code = {"missing": "UNVERIFIABLE", "fail": "UNMET_CONDITION",
            "invalid": "UNVERIFIABLE", "pass": "CONDITION_PASSED"}[kind]
    assert any(issue.condition_id == "C2" and issue.code == code for issue in result.warnings)


@pytest.mark.parametrize("mutation", [
    lambda s: s[0].update(expect=[]),
    lambda s: s[0].update(steps=[{"t_ms": 0, "set": {"Y0": 1}}]),
    lambda s: s[0]["expect"][0].update(t_ms=1),
    lambda s: s[0]["expect"][0].update(value="0"),
    lambda s: s[0]["expect"][0].update(dev="UNKNOWN"),
    lambda s: s[0]["expect"][0].update(dev="M999"),
    lambda s: s[0]["expect"][0].update(t_ms=1_000_000),
    lambda s: s[0]["steps"].append({"t_ms": 0, "set": {}}),
    lambda s: s[0].update(typo=1),
])
def test_unexecutable_required_scenarios_never_pass(mutation):
    req, ir, scenarios = load_scenarios("self_hold")
    mutation(scenarios)
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert any(issue.code == "UNVERIFIABLE" and issue.condition_id == "C1" for issue in result.errors)


@pytest.mark.parametrize("mutation", [
    lambda s: s[0].update(condition_id="UNKNOWN"),
    lambda s: s.append(None),
])
def test_unknown_or_unattributable_scenario_is_not_ignored(mutation):
    req, ir, scenarios = load_scenarios("self_hold")
    mutation(scenarios)
    assert not verify(req, ir, scenarios).passed


def test_all_scenarios_for_same_condition_must_pass():
    req, ir, scenarios = load_scenarios("self_hold")
    wrong = deepcopy(scenarios[0])
    wrong["expect"][1]["value"] = 0
    scenarios.append(wrong)
    assert not verify(req, ir, scenarios).passed


def test_scenarios_are_independent_and_inputs_not_modified():
    req, ir, scenarios = load_scenarios("self_hold")
    idle = {"condition_id": "C1", "steps": [{"t_ms": 0, "set": {"STOP": 1}}],
            "expect": [{"t_ms": 0, "dev": "MOTOR", "value": 0}]}
    scenarios.append(idle)
    before = (req.model_dump(), ir.model_dump(), deepcopy(scenarios))
    result = verify(req, ir, scenarios)
    assert result.passed
    assert before == (req.model_dump(), ir.model_dump(), scenarios)
    assert result == verify(req, ir, scenarios)


@pytest.mark.parametrize("code,change", [
    ("INVALID_OUTPUT_DEVICE", lambda ir: setattr(ir.rungs[0].outputs[0], "target", "X1")),
    ("UNREGISTERED_IO", lambda ir: setattr(ir.rungs[0].outputs[0], "target", "YF")),
    ("UNKNOWN_SIGNAL", lambda ir: setattr(ir.rungs[0].outputs[0], "target", "MISSING")),
    ("DOUBLE_COIL", lambda ir: ir.rungs.append(ir.rungs[0].model_copy(update={"id": "R2"}, deep=True))),
])
def test_static_errors_prevent_simulation(code, change, monkeypatch):
    import app.plc.verify as module

    req, ir, scenarios = load_scenarios("self_hold")
    change(ir)
    def forbidden(*args, **kwargs):
        pytest.fail("정적 검사 실패 회로가 실행되면 안 돼요.")
    monkeypatch.setattr(module, "run", forbidden)
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert code in {issue.code for issue in result.errors}


def test_double_coil_detects_address_and_name_alias():
    req, ir, scenarios = load_scenarios("self_hold")
    duplicate = ir.rungs[0].model_copy(update={"id": "R2"}, deep=True)
    duplicate.outputs[0].target = "MOTOR"
    ir.rungs.append(duplicate)
    assert any(issue.code == "DOUBLE_COIL" for issue in verify(req, ir, scenarios).errors)


def test_zero_timer_is_rejected_by_existing_rules():
    req, ir, scenarios = load_scenarios("on_delay")
    ir.rungs[1].outputs[0].preset_ms = 0
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert any(issue.code == "INVALID_TIMER_PRESET" for issue in result.errors)


@pytest.mark.parametrize("kind", ["empty", "no_required", "duplicate_id", "blank_id"])
def test_incomplete_condition_list_is_not_overall_success(kind):
    req, ir, scenarios = load_scenarios("self_hold")
    if kind == "empty":
        req.conditions = []
    elif kind == "no_required":
        for condition in req.conditions:
            condition.must_pass = False
    elif kind == "duplicate_id":
        req.conditions[1].id = "C1"
    else:
        req.conditions[0].id = ""
    assert not verify(req, ir, scenarios).passed


def test_passed_and_errors_follow_contract():
    for passed, errors in [(True, [{"code": "TEST", "message": "오류"}]), (False, [])]:
        with pytest.raises(ValidationError):
            VerificationResult(passed=passed, errors=errors)
    req, ir, scenarios = load_scenarios("self_hold")
    for supplied in (scenarios, scenarios[:1]):
        result = verify(req, ir, supplied)
        assert result.passed == (not result.errors)
        assert VerificationResult.model_validate_json(result.model_dump_json()) == result


def test_good_and_broken_reports_can_be_opened_without_custom_contract(tmp_path):
    req, ir, scenarios = load_scenarios("self_hold")
    normal = verify(req, ir, scenarios)
    ir.rungs[0].condition = ir.rungs[0].condition.items[0]
    broken = verify(req, ir, scenarios)
    path = tmp_path / "reports.json"
    path.write_text(json.dumps({"normal": normal.model_dump(), "broken": broken.model_dump()},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    opened = json.loads(path.read_text(encoding="utf-8"))
    assert opened["normal"]["passed"] and not opened["broken"]["passed"]
    assert any(issue["condition_id"] == "C2" and "100ms" in issue["message"]
               for issue in opened["broken"]["errors"])


def test_estop_missing_from_either_output_is_a_dynamic_failure():
    req, ir, scenarios = load_scenarios("estop_interlock")
    for index in (0, 1):
        broken = ir.model_copy(deep=True)
        broken.rungs[index].condition.items = [
            item for item in broken.rungs[index].condition.items
            if getattr(item, "signal", None) != "X0"
        ]
        result = verify(req, broken, scenarios)
        assert not result.passed
        assert any(issue.code == "UNMET_CONDITION" and issue.condition_id == "C3"
                   and "100ms" in issue.message for issue in result.errors)


@pytest.mark.parametrize("delay,time,actual", [(4900, "4990ms", "1"), (5100, "5000ms", "0")])
def test_incorrect_timer_threshold_fails_exact_required_boundary(delay, time, actual):
    req, ir, scenarios = load_scenarios("on_delay_5s")
    ir.rungs[1].outputs[0].preset_ms = delay
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert any(issue.condition_id == "C2" and time in issue.message
               and f"실제값 {actual}" in issue.message for issue in result.errors)


def test_caller_supplied_internal_range_and_unverified_default_warning():
    req, ir, scenarios = load_scenarios("on_delay")
    assert verify(req, ir, scenarios, internal_limits={"T": 1}).passed
    result = verify(req, ir, scenarios, internal_limits={"T": 0})
    assert not result.passed
    assert any(issue.code == "INVALID_INTERNAL_RANGE" for issue in result.errors)
    result = verify(req, ir, scenarios)
    assert any(issue.code == "TEMPORARY_INTERNAL_LIMITS" for issue in result.warnings)


def test_static_fault_is_not_downgraded_by_optional_condition():
    req, ir, scenarios = load_scenarios("self_hold")
    req.conditions[1].must_pass = False
    duplicate = ir.rungs[0].model_copy(update={"id": "R2", "covers": ["C2"]}, deep=True)
    ir.rungs.append(duplicate)
    result = verify(req, ir, scenarios)
    assert not result.passed
    assert any(issue.code == "DOUBLE_COIL" for issue in result.errors)


@pytest.mark.parametrize("kind", ["TON", "CTU"])
def test_repeated_timer_or_counter_writes_are_rejected(kind):
    from app.contracts import Ir
    from test_sim import rung

    req, _, scenarios = load_scenarios("self_hold")
    target, preset = ("T0", {"preset_ms": 100}) if kind == "TON" else ("C0", {"preset": 2})
    ir = Ir.model_validate({"rungs": [
        rung("R1", "X1", target, kind, **preset),
        rung("R2", "X2", target, kind, **preset),
    ]})
    assert any(issue.code == "DOUBLE_COIL" for issue in verify(req, ir, scenarios).errors)


def test_set_rst_pair_is_not_a_double_out_coil():
    from app.contracts import Ir
    from test_sim import rung

    req, _, _ = load_scenarios("self_hold")
    ir = Ir.model_validate({"rungs": [
        rung("R1", "X1", "Y0", "SET"), rung("R2", "X2", "Y0", "RST"),
    ]})
    req.conditions = req.conditions[:1]
    scenarios = [{
        "condition_id": "C1",
        "steps": [{"t_ms": 0, "set": {"START": 1}}, {"t_ms": 10, "set": {"START": 0}},
                  {"t_ms": 20, "set": {"STOP": 1}}],
        "expect": [{"t_ms": 0, "dev": "MOTOR", "value": 1},
                   {"t_ms": 10, "dev": "MOTOR", "value": 1},
                   {"t_ms": 20, "dev": "MOTOR", "value": 0}],
    }]
    assert verify(req, ir, scenarios).passed


def test_missing_preset_and_invalid_instruction_are_rejected_by_existing_contract():
    from app.contracts import Output

    for value in ({"kind": "TON", "target": "T0"}, {"kind": "CTU", "target": "C0"},
                  {"kind": "UNKNOWN", "target": "Y0"}):
        with pytest.raises(ValidationError):
            Output.model_validate(value)

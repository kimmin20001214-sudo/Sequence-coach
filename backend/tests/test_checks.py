"""check(시험 틀) → 시험 대본 변환과, 틀만으로 회로를 판정하는 흐름."""
import json

import pytest

from app.contracts import Check, Ir, StructuredRequirements
from app.plc.checks import CheckError, build_scenarios, scenarios_for
from app.plc.scenario import Scenario
from app.plc.verify import verify_with_checks
from test_sim import FIXTURES

CASES = json.loads((FIXTURES / "ir_cases.json").read_text(encoding="utf-8"))
PLC = CASES["self_hold"]["requirements"]["plc_config"]


def C(sig, kind="NO"):
    return {"type": "contact", "kind": kind, "signal": sig}


def OUT(target, kind="OUT", **kw):
    return {"kind": kind, "target": target, **kw}


def ir_of(*rungs):
    return Ir.model_validate({"version": 1, "rungs": [
        {"id": f"R{i + 1}", "condition": cond, "outputs": outs, "covers": ["C1"]}
        for i, (cond, outs) in enumerate(rungs)
    ]})


def AND(*items):
    return {"type": "AND", "items": list(items)}


def OR(*items):
    return {"type": "OR", "items": list(items)}


IO = [
    {"device": "X1", "name": "START", "kind": "푸시버튼 NO", "desc": ""},
    {"device": "X2", "name": "STOP", "kind": "푸시버튼 NC", "desc": ""},
    {"device": "X3", "name": "B", "kind": "푸시버튼 NO", "desc": ""},
    {"device": "Y0", "name": "MOTOR", "kind": "모터", "desc": ""},
    {"device": "Y1", "name": "LAMP", "kind": "램프", "desc": ""},
]


def req_with(check, timers=None):
    return StructuredRequirements.model_validate({
        "plc_config": PLC, "io_list": IO,
        "conditions": [{"id": "C1", "type": "sequence", "text": "t", "must_pass": True, "check": check}],
        "timers": timers or [],
    })


def run_check(check, ir, timers=None):
    return verify_with_checks(req_with(check, timers), ir)


def passed_by_check(result):
    return any(w.code == "CONDITION_PASSED" for w in result.warnings)


HOLD = (AND(OR(C("X1"), C("Y0")), C("X2")), [OUT("Y0")])

SELF_HOLD = {"pattern": "self_hold", "start": "START", "stop": "STOP", "output": "MOTOR"}


def test_self_hold_passes_and_catches_missing_stop():
    result = run_check(SELF_HOLD, ir_of(HOLD))
    assert result.passed and passed_by_check(result)
    no_stop = ir_of((OR(C("X1"), C("Y0")), [OUT("Y0")]))
    assert not run_check(SELF_HOLD, no_stop).passed


def test_self_hold_catches_missing_hold():
    result = run_check(SELF_HOLD, ir_of((AND(C("X1"), C("X2")), [OUT("Y0")])))
    assert not result.passed
    assert any("기대값 1" in e.message for e in result.errors)


def test_stop_priority_passes_and_catches_override():
    check = {"pattern": "stop_priority", "stop": "STOP", "outputs": ["MOTOR"]}
    assert run_check(check, ir_of(HOLD)).passed
    assert not run_check(check, ir_of((OR(C("X1"), C("Y0")), [OUT("Y0")]))).passed


ON_DELAY = {"pattern": "on_delay", "trigger": "START", "output": "MOTOR", "delay_ms": 3000, "stop": "STOP"}
TIMER = [{"name": "T0", "preset_ms": 3000}]


def delay_ir(preset=3000):
    return ir_of(
        (AND(C("X1"), C("X2")), [OUT("T0", "TON", preset_ms=preset)]),
        (C("T0"), [OUT("Y0")]),
    )


def test_on_delay_passes_and_catches_wrong_time():
    assert run_check(ON_DELAY, delay_ir(), TIMER).passed
    assert not run_check(ON_DELAY, delay_ir(1000), TIMER).passed
    assert not run_check(ON_DELAY, delay_ir(5000), TIMER).passed
    assert not run_check(ON_DELAY, ir_of((C("X1"), [OUT("Y0")])), TIMER).passed


def test_timed_on_passes_and_catches_never_stopping():
    check = {"pattern": "timed_on", "trigger": "START", "output": "MOTOR", "duration_ms": 2000}
    good = ir_of(
        (OR(C("X1"), AND(C("Y0"), C("T0", "NC"))), [OUT("Y0")]),
        (C("Y0"), [OUT("T0", "TON", preset_ms=2000)]),
    )
    assert run_check(check, good, [{"name": "T0", "preset_ms": 2000}]).passed
    forever = ir_of((OR(C("X1"), C("Y0")), [OUT("Y0")]))
    assert not run_check(check, forever).passed


def test_interlock_passes_and_catches_simultaneous_outputs():
    check = {"pattern": "interlock", "a": "MOTOR", "b": "LAMP"}
    good = ir_of((C("X1"), [OUT("Y0")]), (AND(C("X3"), C("Y0", "NC")), [OUT("Y1")]))
    assert run_check(check, good).passed
    bad = ir_of((C("X1"), [OUT("Y0")]), (C("X3"), [OUT("Y1")]))
    result = run_check(check, bad)
    assert not result.passed and any("동시에 켜졌어요" in e.message for e in result.errors)


def test_and_enable_and_or_enable():
    check = {"pattern": "and_enable", "inputs": ["START", "B"], "output": "MOTOR"}
    assert run_check(check, ir_of((AND(C("X1"), C("X3")), [OUT("Y0")]))).passed
    assert not run_check(check, ir_of((C("X1"), [OUT("Y0")]))).passed
    check = {"pattern": "or_enable", "inputs": ["START", "B"], "output": "MOTOR"}
    assert run_check(check, ir_of((OR(C("X1"), C("X3")), [OUT("Y0")]))).passed
    assert not run_check(check, ir_of((C("X1"), [OUT("Y0")]))).passed


def test_indicator_follows_output():
    check = {"pattern": "indicator", "output": "MOTOR", "lamp": "LAMP"}
    assert run_check(check, ir_of((C("X1"), [OUT("Y0")]), (C("Y0"), [OUT("Y1")]))).passed
    assert run_check(check, ir_of((C("X1"), [OUT("Y0")]), (C("X1"), [OUT("Y1")]))).passed
    result = run_check(check, ir_of((C("X1"), [OUT("Y0")]), (C("X3"), [OUT("Y1")])))
    assert not result.passed


def test_set_reset():
    check = {"pattern": "set_reset", "set_input": "START", "reset_input": "B", "output": "MOTOR"}
    good = ir_of((C("X1"), [OUT("Y0", "SET")]), (C("X3"), [OUT("Y0", "RST")]))
    assert run_check(check, good).passed
    assert not run_check(check, ir_of((C("X1"), [OUT("Y0", "SET")]))).passed


def test_custom_passes_through_and_is_flagged_low_confidence():
    check = {"pattern": "custom",
             "steps": [{"t_ms": 0, "set": {"STOP": 1}}, {"t_ms": 100, "set": {"START": 1}}],
             "expect": [{"t_ms": 200, "dev": "MOTOR", "value": 1}]}
    result = run_check(check, ir_of(HOLD))
    assert result.passed
    assert any(w.code == "CUSTOM_CHECK_LOW_CONFIDENCE" for w in result.warnings)


@pytest.mark.parametrize("check, text", [
    ({"pattern": "self_hold", "start": "NOPE", "stop": "STOP", "output": "MOTOR"}, "I/O 목록에 없어요"),
    ({"pattern": "self_hold", "start": "START", "stop": "STOP", "output": "START"}, "출력(Y)"),
    ({"pattern": "self_hold", "start": "MOTOR", "stop": "STOP", "output": "MOTOR"}, "입력(X)"),
    ({"pattern": "self_hold"}, "비어"),
    ({"pattern": "on_delay", "trigger": "START", "output": "MOTOR"}, "delay_ms"),
    ({"pattern": "on_delay", "trigger": "START", "output": "MOTOR", "delay_ms": 3005}, "배수"),
    ({"pattern": "timed_on", "trigger": "START", "output": "MOTOR", "duration_ms": 100}, "200ms"),
    ({"pattern": "stop_priority", "stop": "STOP", "outputs": []}, "하나 이상"),
    ({"pattern": "interlock", "a": "MOTOR", "b": "MOTOR"}, "서로 다른"),
    ({"pattern": "and_enable", "inputs": ["START"], "output": "MOTOR"}, "두 개 이상"),
    ({"pattern": "custom"}, "steps와 expect"),
])
def test_invalid_checks_become_required_failures(check, text):
    req = req_with(check)
    scenarios, problems = build_scenarios(req)
    assert scenarios == [] and text in problems[0][1]
    result = verify_with_checks(req, ir_of(HOLD))
    assert not result.passed
    assert any(e.code == "INVALID_CHECK" for e in result.errors)


def test_unknown_pattern_or_extra_field_is_rejected_by_contract():
    with pytest.raises(Exception):
        Check.model_validate({"pattern": "magic"})
    with pytest.raises(Exception):
        Check.model_validate({"pattern": "self_hold", "typo": 1})


@pytest.mark.parametrize("pattern", ["self_hold", "stop_priority", "on_delay", "timed_on", "interlock",
                                     "and_enable", "or_enable", "indicator", "set_reset"])
def test_every_generated_scenario_is_valid_format(pattern):
    checks = {
        "self_hold": SELF_HOLD,
        "stop_priority": {"pattern": "stop_priority", "stop": "STOP", "outputs": ["MOTOR", "LAMP"]},
        "on_delay": ON_DELAY,
        "timed_on": {"pattern": "timed_on", "trigger": "START", "output": "MOTOR", "duration_ms": 2000},
        "interlock": {"pattern": "interlock", "a": "MOTOR", "b": "LAMP"},
        "and_enable": {"pattern": "and_enable", "inputs": ["START", "B"], "output": "MOTOR"},
        "or_enable": {"pattern": "or_enable", "inputs": ["START", "B"], "output": "MOTOR"},
        "indicator": {"pattern": "indicator", "output": "MOTOR", "lamp": "LAMP"},
        "set_reset": {"pattern": "set_reset", "set_input": "START", "reset_input": "B", "output": "MOTOR"},
    }
    req = req_with(checks[pattern])
    scenarios = scenarios_for(req, "C1", req.conditions[0].check)
    assert scenarios
    for raw in scenarios:
        Scenario.model_validate(raw)
        assert all(s["t_ms"] % 10 == 0 for s in raw["steps"])


@pytest.mark.parametrize("name, checks", [
    ("self_hold", {"C1": SELF_HOLD,
                   "C2": {"pattern": "stop_priority", "stop": "STOP", "outputs": ["MOTOR"]}}),
    ("estop_interlock", {
        "C1": {"pattern": "self_hold", "start": "START", "stop": "STOP", "output": "MOTOR_FWD"},
        "C2": {"pattern": "interlock", "a": "MOTOR_FWD", "b": "MOTOR_REV"},
        "C3": {"pattern": "stop_priority", "stop": "EMG", "outputs": ["MOTOR_FWD", "MOTOR_REV"]},
        "C5": {"pattern": "stop_priority", "stop": "STOP", "outputs": ["MOTOR_FWD", "MOTOR_REV"]},
    }),
])
def test_existing_good_circuits_pass_with_checks_only(name, checks):
    case = CASES[name]
    req = StructuredRequirements.model_validate(case["requirements"])
    for cond in req.conditions:
        cond.check = Check.model_validate(checks[cond.id]) if cond.id in checks else None
    req.conditions = [c for c in req.conditions if c.check]
    result = verify_with_checks(req, Ir.model_validate(case["ir"]))
    assert result.passed, [e.message for e in result.errors]
    assert sum(w.code == "CONDITION_PASSED" for w in result.warnings) == len(req.conditions)

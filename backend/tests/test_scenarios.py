"""손으로 작성한 시나리오의 형식과 정상 회로에서의 기대값을 검사한다."""
import json

import pytest
from pydantic import ValidationError

from app.contracts import Ir, StructuredRequirements
from app.plc.scenario import Scenario
from app.plc.sim import Signals, run
from test_sim import FIXTURES

SCENARIO_NAMES = ["self_hold", "on_delay", "on_delay_5s", "estop_interlock", "normal_operation"]


def load_scenarios(name):
    data = json.loads((FIXTURES / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))
    cases = json.loads((FIXTURES / "ir_cases.json").read_text(encoding="utf-8"))
    case = cases[data["fixture"]]
    req = StructuredRequirements.model_validate(case["requirements"])
    ir = Ir.model_validate(case["ir"])
    if "timer_preset_ms" in data:
        req.timers[0].preset_ms = data["timer_preset_ms"]
        ir.rungs[1].outputs[0].preset_ms = data["timer_preset_ms"]
    return req, ir, data["scenarios"]


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_handwritten_scenarios_cover_conditions_and_match_good_circuit(name):
    req, ir, scenarios = load_scenarios(name)
    assert {s["condition_id"] for s in scenarios} == {c.id for c in req.conditions}
    signals = Signals(req.io_list)
    for raw in scenarios:
        scenario = Scenario.model_validate(raw)
        end = max([s.t_ms for s in scenario.steps] + [e.t_ms for e in scenario.expect])
        trace = run(ir, [s.model_dump() for s in scenario.steps], io_list=req.io_list, until_ms=end)
        for expected in scenario.expect:
            assert trace[expected.t_ms // 10]["state"][signals.resolve(expected.dev)] == expected.value


@pytest.mark.parametrize("change", [
    {"condition_id": ""}, {"condition_id": " "}, {"expect": []},
    {"expect": [{"t_ms": -1, "dev": "Y0", "value": 1}]},
    {"expect": [{"t_ms": 0, "dev": "", "value": 1}]},
    {"expect": [{"t_ms": 0, "dev": "Y0", "value": 2}]},
    {"expect": [{"t_ms": 0, "dev": "Y0", "value": "1"}]},
    {"expect": [{"t_ms": True, "dev": "Y0", "value": 1}]},
    {"steps": [{"t_ms": 0, "set": {"X1": 2}}]},
    {"typo": 1},
])
def test_invalid_scenario_schema_is_rejected(change):
    value = {"condition_id": "C1", "steps": [],
             "expect": [{"t_ms": 0, "dev": "Y0", "value": 0}], **change}
    with pytest.raises(ValidationError):
        Scenario.model_validate(value)

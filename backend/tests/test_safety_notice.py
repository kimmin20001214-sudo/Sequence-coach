"""안전 고지가 설계·검증 결과에서 빠지지 않는지 검사한다."""
import pytest

from app.plc.design_check import check_design
from app.plc.verify import verify
from test_scenarios import SCENARIO_NAMES, load_scenarios

KEYWORD = "전문가 확인 필요"


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_verification_always_carries_safety_notice(name):
    req, ir, scenarios = load_scenarios(name)
    result = verify(req, ir, scenarios)
    assert any(w.code == "SIMULATION_ONLY" and KEYWORD in w.message for w in result.warnings)


def test_failed_verification_still_carries_safety_notice():
    req, ir, scenarios = load_scenarios("self_hold")
    ir.rungs[0].outputs[0].target = "X1"
    result = verify(req, ir, scenarios)
    assert result.errors
    assert any(w.code == "SIMULATION_ONLY" and KEYWORD in w.message for w in result.warnings)


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_design_limitations_carry_safety_notice(name):
    req, ir, _ = load_scenarios(name)
    result, problems = check_design(req, ir)
    if result is not None:
        assert any(KEYWORD in text for text in result.limitations)

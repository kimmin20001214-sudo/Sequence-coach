"""요구사항으로 생성한 자기유지 회로의 구조와 버튼 동작을 확인한다."""

import pytest

from app.contracts import Contact, Ir, Parallel, StructuredRequirements
from app.plc.self_hold import design_self_hold
from app.spec import load_instructions
from test_contracts import load


@pytest.fixture
def requirements():
    return StructuredRequirements.model_validate(load("self_hold")["requirements"])


def evaluate(node, values):
    if isinstance(node, Contact):
        return values[node.signal] if node.kind == "NO" else not values[node.signal]
    results = [evaluate(item, values) for item in node.items]
    return any(results) if isinstance(node, Parallel) else all(results)


def test_generated_ir_matches_example(requirements):
    before = requirements.model_dump()
    expected = Ir.model_validate(load("self_hold")["ir"])
    assert design_self_hold(requirements) == expected
    assert requirements.model_dump() == before


def test_changed_addresses_and_condition_ids(requirements):
    for row, address in zip(requirements.io_list, ["X1A", "X1B", "Y1F"]):
        row.device = address
    requirements.conditions[0].signals = ["X1A", "Y1F"]
    requirements.conditions[1].signals = ["X1B", "Y1F"]
    requirements.conditions[0].id = "C10"
    requirements.conditions[1].id = "C20"
    rung = design_self_hold(requirements).rungs[0]
    assert [item.signal for item in rung.condition.items[0].items] == ["X1A", "Y1F"]
    assert rung.condition.items[1].signal == "X1B"
    assert rung.outputs[0].target == "Y1F"
    assert rung.covers == ["C10", "C20"]


@pytest.mark.parametrize("role", ["START", "STOP", "MOTOR"])
def test_missing_required_signal(requirements, role):
    requirements.io_list = [row for row in requirements.io_list if row.name != role]
    with pytest.raises(ValueError, match=f"필요한 신호가 없어요: {role}"):
        design_self_hold(requirements)


@pytest.mark.parametrize("kind, released, pressed, contact_kind", [
    ("푸시버튼 NC", True, False, "NO"),
    ("푸시버튼 NO", False, True, "NC"),
])
def test_stop_polarity_and_self_hold(requirements, kind, released, pressed, contact_kind):
    requirements.io_list[1].kind = kind
    rung = design_self_hold(requirements).rungs[0]
    assert rung.condition.items[1].kind == contact_kind
    motor = False
    for start, stop, expected in [
        (False, released, False),
        (True, released, True),
        (False, released, True),
        (True, pressed, False),
        (False, released, False),
    ]:
        motor = evaluate(rung.condition, {"X1": start, "X2": stop, "Y0": motor})
        assert motor is expected


def test_nc_start_button(requirements):
    requirements.io_list[0].kind = "푸시버튼 NC"
    rung = design_self_hold(requirements).rungs[0]
    assert rung.condition.items[0].items[0].kind == "NC"
    assert not evaluate(rung.condition, {"X1": True, "X2": True, "Y0": False})
    assert evaluate(rung.condition, {"X1": False, "X2": True, "Y0": False})


def test_unknown_condition_signal(requirements):
    requirements.conditions[0].signals.append("X3")
    with pytest.raises(ValueError, match="등록되지 않은 신호예요: X3"):
        design_self_hold(requirements)


@pytest.mark.parametrize("device", ["XGG", "Y1", "X2000", "X2"])
def test_invalid_input_address(requirements, device):
    requirements.io_list[0].device = device
    with pytest.raises(ValueError, match="주소"):
        design_self_hold(requirements)


def test_unknown_button_polarity(requirements):
    requirements.io_list[1].kind = "푸시버튼"
    with pytest.raises(ValueError, match="푸시버튼 NO 또는 푸시버튼 NC"):
        design_self_hold(requirements)


def test_disallowed_instruction(requirements, monkeypatch):
    data = load_instructions()
    allowed = [item for item in data["series"]["Q"] if item != "OUT"]
    monkeypatch.setattr("app.plc.self_hold.load_instructions", lambda: {"series": {"Q": allowed}})
    with pytest.raises(ValueError, match="허용하지 않는 명령어예요: OUT"):
        design_self_hold(requirements)


@pytest.mark.parametrize("change", ["questions", "emergency_stop", "timers", "language", "conditions"])
def test_unsupported_requirements_are_not_completed(requirements, change):
    if change == "questions":
        requirements.questions = ["입력을 확인해 주세요."]
    elif change == "emergency_stop":
        requirements.plc_config.emergency_stop.used = True
    elif change == "timers":
        requirements.timers = [{"name": "T0", "preset_ms": 1000}]
    elif change == "language":
        requirements.plc_config.language = "ST"
    else:
        requirements.conditions.pop()
    with pytest.raises(ValueError):
        design_self_hold(requirements)


def test_non_self_hold_sequence_is_rejected(requirements):
    requirements.conditions[0].text = "START를 누르는 동안만 MOTOR가 켜진다."
    with pytest.raises(ValueError, match="지원하지 않는 자기유지 조건"):
        design_self_hold(requirements)

"""명시 지시의 성공·거부·입력 불변성 및 초안 논리 검사."""
import json
from itertools import product
from pathlib import Path

import pytest

from app.contracts import Condition, CounterSpec, StructuredRequirements, TimerSpec
from app.plc import design
from app.plc.design import DesignError, PREFIX, SAFETY_NOTICE, design_circuit
from app.plc.rules import validate_ir
from app.plc.to_il import IrConversionError, to_il
from app.schemas import IoRow
from app.spec import load_instructions
from test_plc import evaluate_il, evaluate_node

FIXTURES = Path(__file__).parent / "fixtures"


def load_case(name="self_hold"):
    original = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    case = json.loads((FIXTURES / "design_cases.json").read_text(encoding="utf-8"))[name]
    req = StructuredRequirements.model_validate(original["requirements"])
    req.io_list.extend(IoRow.model_validate(row) for row in case["extra_io"])
    req.conditions.extend(Condition.model_validate(c) for c in case["extra_conditions"])
    req.assumptions.extend(PREFIX + json.dumps(d, ensure_ascii=False) for d in case["directives"])
    return req, case["expected_il"]


def directives(req):
    return [json.loads(text[len(PREFIX):]) for text in req.assumptions if text.startswith(PREFIX)]


def replace_directives(req, rules):
    req.assumptions = [text for text in req.assumptions if not text.startswith(PREFIX)]
    req.assumptions.extend(PREFIX + json.dumps(rule, ensure_ascii=False) for rule in rules)


@pytest.fixture
def req():
    return load_case()[0]


@pytest.mark.parametrize("name", ["self_hold", "on_delay", "estop_interlock"])
def test_design_examples_and_input_immutability(name):
    req, expected = load_case(name)
    before = req.model_dump()
    result = design_circuit(req)
    assert result.il == expected
    assert result.il[-1] == "END"
    assert validate_ir(result.ir, req.plc_config, req.io_list, internal_limits=design.TEMPORARY_LIMITS).passed
    assert to_il(result.ir, req.plc_config, req.io_list, internal_limits=design.TEMPORARY_LIMITS) == result.il
    assert req.model_dump() == before
    assert result.assumptions == req.assumptions
    assert SAFETY_NOTICE in result.limitations
    assert any("매뉴얼 미확인" in text for text in result.limitations)
    assert {e["rung_id"] for e in result.explanation} == {r.id for r in result.ir.rungs}
    assert {cid for r in result.ir.rungs for cid in r.covers} == {c.id for c in req.conditions}
    for rung, explanation in zip(result.ir.rungs, result.explanation):
        assert explanation["condition_ids"] == rung.covers
        assert all(cid in explanation["text"] for cid in rung.covers)
        assert all(output.target in explanation["text"] for output in rung.outputs)
    assert {row.device for row in result.io_used} == {row.device for row in req.io_list}


def test_self_hold_truth_table_and_nc_stop(req):
    result = design_circuit(req)
    for start, stop, previous in product((False, True), repeat=3):
        values = {"X1": start, "X2": stop, "Y0": previous}
        expected = (start or previous) and stop
        assert evaluate_node(result.ir.rungs[0].condition, values) == expected
        assert evaluate_il(result.il, values)["Y0"] == expected


def test_estop_gates_every_output_and_real_interlock_direction():
    req, _ = load_case("estop_interlock")
    result = design_circuit(req)
    for start, reverse, stop, emg, old_fwd in product((False, True), repeat=5):
        values = {"X1": start, "X3": reverse, "X2": stop, "X0": emg, "Y0": old_fwd, "Y1": False}
        for rung in result.ir.rungs:
            powered = evaluate_node(rung.condition, values)
            for output in rung.outputs:
                values[output.target] = powered
        assert values["Y0"] == ((start or old_fwd) and stop and emg)
        assert values["Y1"] == (reverse and not values["Y0"] and stop and emg)
        if not emg or not stop:
            assert not values["Y0"] and not values["Y1"]
    assert "C2" not in result.ir.rungs[0].covers
    assert "C2" in result.ir.rungs[1].covers


def test_only_explicit_directives_not_text_keywords(req):
    for condition in req.conditions:
        condition.text = "글 문장은 실행하지 않습니다."
    req.assumptions.insert(0, "direct mode를 예상했어요.")
    assert design_circuit(req).il == load_case()[1]
    req.assumptions = ["자기유지 STOP 동작을 가정했어요."]
    with pytest.raises(DesignError, match="C1.*설계 지시"):
        design_circuit(req)


def test_multiple_inputs_outputs_internal_start_and_real_io(req):
    req.io_list.extend([
        IoRow(device="X3", name="SECOND", kind="센서"),
        IoRow(device="Y1", name="LAMP", kind="램프"),
        IoRow(device="X4", name="UNUSED", kind="센서"),
    ])
    req.conditions[0].signals = ["START", "SECOND", "MOTOR", "LAMP"]
    req.conditions[1].signals = ["STOP", "MOTOR", "LAMP"]
    rules = directives(req)
    rules[0]["inputs"].append({"signal": "SECOND", "active": "off"})
    rules[0]["join"] = "any"
    for rule in rules:
        rule["outputs"].append("LAMP")
    replace_directives(req, rules)
    req.plc_config.device_rule.M = 10
    result = design_circuit(req)
    assert "OUT M10" in result.il and "MPS" in result.il
    assert {row.device for row in result.io_used} == {"X1", "X2", "X3", "Y0", "Y1"}
    assert any("M10" in e["text"] for e in result.explanation)
    for start, second, stop, old_hold in product((False, True), repeat=4):
        values = {"X1": start, "X3": second, "X2": stop, "M10": old_hold}
        for rung in result.ir.rungs:
            value = evaluate_node(rung.condition, values)
            for output in rung.outputs:
                values[output.target] = value
        expected = (start or not second or old_hold) and stop
        assert values["Y0"] == values["Y1"] == expected


def test_direct_multiple_outputs(req):
    req.io_list.append(IoRow(device="Y1", name="LAMP", kind="램프"))
    req.conditions[0].signals.append("LAMP")
    req.conditions[1].signals.append("LAMP")
    rules = directives(req)
    rules[0]["mode"] = "direct"
    for rule in rules:
        rule["outputs"].append("LAMP")
    replace_directives(req, rules)
    result = design_circuit(req)
    assert result.il == ["LD X1", "AND X2", "MPS", "OUT Y0", "MPP", "OUT Y1", "END"]


def test_timer_mapping_start_and_dependency_order():
    req, _ = load_case("on_delay")
    req.timers[0].name = "LAMP_DELAY"
    req.plc_config.device_rule.T = 20
    rules = directives(req)
    rules[1]["timer"] = "LAMP_DELAY"
    replace_directives(req, list(reversed(rules)))
    result = design_circuit(req)
    assert result.il == ["LD X1", "OUT Y0", "LD Y0", "OUT T20 K30", "LD T20", "OUT Y1", "END"]
    assert all(not row.device.startswith("T") for row in result.io_used)


def test_counter_with_explicit_no_reset(req):
    rules = directives(req)
    rules[0].update(mode="count", counter="PARTS", reset="none")
    req.counters = [CounterSpec(name="PARTS", preset=5)]
    req.plc_config.device_rule.C = 7
    replace_directives(req, rules)
    result = design_circuit(req)
    assert result.il == ["LD X1", "AND X2", "OUT C7 K5", "LD C7", "AND X2", "OUT Y0", "END"]
    assert any("리셋하지" in text for text in result.limitations)


@pytest.mark.parametrize("field,value,match", [
    ("questions", ["시간은?"], "질문"),
    ("assumptions", [], "설계 지시"),
])
def test_missing_information(req, field, value, match):
    setattr(req, field, value)
    with pytest.raises(DesignError, match=f"C1.*{match}"):
        design_circuit(req)


@pytest.mark.parametrize("field,value", [
    ("series", "iQ-R"), ("language", "st"), ("software", "GX Works3"),
    ("cpu", "UNKNOWN"), ("retentive", True), ("alarm", True),
    ("modules", ["아날로그 입력"]), ("modes", ["수동"]),
    ("x_points", 1), ("timer_unit_ms", 10),
])
def test_unsupported_config(req, field, value):
    setattr(req.plc_config, field, value)
    with pytest.raises(DesignError, match="조건 C1"):
        design_circuit(req)


@pytest.mark.parametrize("cid", ["", " C1", "C2"])
def test_bad_condition_ids(req, cid):
    req.conditions[0].id = cid
    with pytest.raises(DesignError, match="ID"):
        design_circuit(req)


@pytest.mark.parametrize("signal", ["MISSING", "X7", "M0"])
def test_unregistered_signal(req, signal):
    req.conditions[0].signals[0] = signal
    with pytest.raises(DesignError, match="C1.*등록"):
        design_circuit(req)


@pytest.mark.parametrize("mutation", [
    lambda rules: rules.append(rules[0].copy()),
    lambda rules: rules[0].pop("join"),
    lambda rules: rules[0].update(condition_id="UNKNOWN"),
    lambda rules: rules[0].update(mode="guessed"),
    lambda rules: rules[0].update(extra=True),
    lambda rules: rules[0]["inputs"][0].pop("active"),
    lambda rules: rules[0]["inputs"][0].update(active="guess"),
    lambda rules: rules[0].update(inputs=[]),
    lambda rules: rules[0].update(outputs=[]),
    lambda rules: rules[0]["inputs"].append({"signal": "START", "active": "off"}),
    lambda rules: rules[0]["outputs"].append("START"),
    lambda rules: rules[0].update(outputs=["UNKNOWN"]),
    lambda rules: rules[0].update(inputs=[{"signal": "STOP", "active": "on"}]),
    lambda rules: rules[0].update(timer="T0"),
])
def test_invalid_or_conflicting_directives(req, mutation):
    rules = directives(req)
    mutation(rules)
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="조건"):
        design_circuit(req)


@pytest.mark.parametrize("text", [
    PREFIX + "{", PREFIX + "[]",
    PREFIX + '{"condition_id":"C1","condition_id":"C2","mode":"direct"}',
])
def test_bad_json_and_duplicate_keys(req, text):
    req.assumptions.insert(0, text)
    with pytest.raises(DesignError, match="조건.*형식"):
        design_circuit(req)


@pytest.mark.parametrize("must_pass", [True, False])
def test_unimplemented_condition_never_fake_covers(req, must_pass):
    req.conditions.append(Condition(id="C3", type="alarm", text="알람 조건", signals=["Y0"], must_pass=must_pass))
    with pytest.raises(DesignError, match="C3.*설계 지시"):
        design_circuit(req)


def test_safety_never_ignored(req):
    req.plc_config.emergency_stop.used = True
    req.plc_config.emergency_stop.device = "X2"
    with pytest.raises(DesignError, match="safety"):
        design_circuit(req)
    req.conditions.append(Condition(id="C3", type="safety", text="정지", signals=["STOP"]))
    replace_directives(req, directives(req) + [{"condition_id": "C3", "mode": "emergency_stop"}])
    result = design_circuit(req)
    assert all("C3" in rung.covers for rung in result.ir.rungs)
    req.io_list[1].kind = "푸시버튼 NO"
    with pytest.raises(DesignError, match="C3.*NC"):
        design_circuit(req)
    req.io_list[1].kind = "푸시버튼 NC"
    req.plc_config.emergency_stop.used = False
    with pytest.raises(DesignError, match="C3"):
        design_circuit(req)


def test_block_requires_real_output_producer(req):
    req.io_list.append(IoRow(device="Y1", name="REV", kind="모터"))
    req.conditions[1].signals = ["STOP", "REV"]
    rules = directives(req)
    rules[1]["outputs"] = ["REV"]
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="C2.*실질"):
        design_circuit(req)


def test_unsupported_condition_type(req):
    req.conditions[0].type = "alarm"
    with pytest.raises(DesignError, match="C1.*sequence"):
        design_circuit(req)


@pytest.mark.parametrize("kind", ["M", "T", "C"])
def test_internal_exclusive_end(req, kind):
    if kind == "T":
        req, _ = load_case("on_delay")
    elif kind == "M":
        req.io_list.append(IoRow(device="Y1", name="LAMP", kind="램프"))
        rules = directives(req)
        for c, rule in zip(req.conditions, rules):
            c.signals.append("LAMP")
            rule["outputs"].append("LAMP")
        replace_directives(req, rules)
    else:
        req.counters = [CounterSpec(name="COUNT", preset=1)]
        rules = directives(req)
        rules[0].update(mode="count", counter="COUNT", reset="none")
        replace_directives(req, rules)
    setattr(req.plc_config.device_rule, kind, design.TEMPORARY_LIMITS[kind])
    with pytest.raises(DesignError, match=f"{kind}.*범위"):
        design_circuit(req)
    setattr(req.plc_config.device_rule, kind, design.TEMPORARY_LIMITS[kind] - 1)
    assert design_circuit(req).il[-1] == "END"


@pytest.mark.parametrize("ms", [0, 1, 3050, 3276800])
def test_timer_error_preserved(ms):
    req, _ = load_case("on_delay")
    req.timers[0].preset_ms = ms
    with pytest.raises(DesignError, match="INVALID_TIMER_PRESET"):
        design_circuit(req)


def test_timer_missing_duplicate_unused_connections():
    for mutation in (
        lambda req: req.timers.clear(),
        lambda req: req.timers.append(req.timers[0].model_copy()),
        lambda req: req.timers.append(TimerSpec(name="UNUSED", preset_ms=100)),
    ):
        req, _ = load_case("on_delay")
        mutation(req)
        with pytest.raises(DesignError, match="타이머"):
            design_circuit(req)


def test_forbidden_instruction_reason_preserved(req, monkeypatch):
    instructions = load_instructions()["series"]
    monkeypatch.setitem(instructions, "Q", [op for op in instructions["Q"] if op != "OR"])
    with pytest.raises(DesignError, match="DISALLOWED_INSTRUCTION.*OR"):
        design_circuit(req)


def test_validate_then_to_il_and_conversion_error(req, monkeypatch):
    calls = []
    real_validate = design.validate_ir

    def validate(*args, **kwargs):
        calls.append("validate")
        return real_validate(*args, **kwargs)

    def convert(*args, **kwargs):
        calls.append("to_il")
        from app.contracts import VerificationIssue, VerificationResult
        raise IrConversionError(VerificationResult(passed=False, errors=[
            VerificationIssue(code="CONVERSION_TEST", message="시험 변환 이유"),
        ]))

    monkeypatch.setattr(design, "validate_ir", validate)
    monkeypatch.setattr(design, "to_il", convert)
    with pytest.raises(DesignError, match="시험 변환 이유"):
        design_circuit(req)
    assert calls == ["validate", "to_il"]


@pytest.mark.parametrize("device,name,kind", [
    ("X01", "ALIAS", "센서"), ("X3", "START", "센서"),
    ("X3", "M0", "센서"), ("XG", "BAD", "센서"),
    ("X3", "", "센서"), ("X3", "Y0", "센서"),
])
def test_bad_io_registration(req, device, name, kind):
    req.io_list.append(IoRow(device=device, name=name, kind=kind))
    with pytest.raises(DesignError, match="조건"):
        design_circuit(req)


def test_unspecified_io_kind_is_not_inferred(req):
    req.io_list[0].kind = "기타"
    with pytest.raises(DesignError, match="C1.*kind"):
        design_circuit(req)


def test_duplicate_producer_and_cyclic_dependency():
    req, _ = load_case("on_delay")
    req.conditions.append(Condition(id="C3", type="sequence", text="추가", signals=["START", "LAMP"]))
    rules = directives(req)
    rules.append({"condition_id": "C3", "mode": "direct", "inputs": [
        {"signal": "START", "active": "on"}], "join": "all", "outputs": ["LAMP"]})
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="C3.*여러 조건"):
        design_circuit(req)
    req, _ = load_case("on_delay")
    req.conditions[0].signals = ["MOTOR", "LAMP"]
    rules = directives(req)
    rules[0]["inputs"][0]["signal"] = "MOTOR"
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="순환"):
        design_circuit(req)


def test_different_gates_for_shared_outputs_is_explicit_error(req):
    req.io_list.append(IoRow(device="Y1", name="LAMP", kind="램프"))
    req.conditions[0].signals.append("LAMP")
    rules = directives(req)
    rules[0]["outputs"].append("LAMP")
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="C1.*조건을 나눠"):
        design_circuit(req)


def test_estop_timer_gates_timer_and_final_output():
    req, _ = load_case("on_delay")
    req.io_list.append(IoRow(device="X0", name="EMG", kind="푸시버튼 NC"))
    req.plc_config.emergency_stop.used = True
    req.plc_config.emergency_stop.device = "X0"
    req.conditions.append(Condition(id="C3", type="safety", text="모든 출력 OFF", signals=["EMG"]))
    replace_directives(req, directives(req) + [{"condition_id": "C3", "mode": "emergency_stop"}])
    result = design_circuit(req)
    assert result.il == [
        "LD X1", "AND X0", "OUT Y0", "LD Y0", "AND X0", "OUT T0 K30",
        "LD T0", "AND X0", "OUT Y1", "END",
    ]
    for rung in result.ir.rungs:
        assert "C3" in rung.covers
        values = {"X1": True, "X0": False, "Y0": True, "T0": True}
        assert not evaluate_node(rung.condition, values)


@pytest.mark.parametrize("preset", [0, 32768])
def test_counter_bad_preset(req, preset):
    req.counters = [CounterSpec(name="COUNT", preset=preset)]
    rules = directives(req)
    rules[0].update(mode="count", counter="COUNT", reset="none")
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="INVALID_COUNTER_PRESET"):
        design_circuit(req)


def test_nc_direct_and_active_high_stop_are_explicit(req):
    rules = directives(req)
    rules[0]["mode"] = "direct"
    rules[0]["inputs"][0]["active"] = "off"
    rules[1]["inputs"][0]["active"] = "on"
    replace_directives(req, rules)
    assert design_circuit(req).il == ["LDI X1", "ANI X2", "OUT Y0", "END"]


def test_series_internal_limits_take_precedence(req, monkeypatch):
    spec = dict(design.get_series("Q"))
    spec["internal_limits"] = {"M": 100, "T": 2, "C": 10}
    monkeypatch.setattr(design, "get_series", lambda series: spec)
    result = design_circuit(req)
    assert not any("M8192" in text for text in result.limitations)
    req, _ = load_case("on_delay")
    req.plc_config.device_rule.T = 2
    with pytest.raises(DesignError, match="T.*범위"):
        design_circuit(req)


def test_empty_timer_name_is_rejected():
    req, _ = load_case("on_delay")
    req.timers[0].name = ""
    rules = directives(req)
    rules[1]["timer"] = ""
    replace_directives(req, rules)
    with pytest.raises(DesignError, match="이름"):
        design_circuit(req)

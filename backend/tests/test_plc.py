"""고정 예시, 논리 진리표, 주소·명령어·시간 경계의 사전 검사."""
import json
from itertools import product
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import Contact, Ir, Output, Parallel, Rung, Series, StructuredRequirements
from app.plc.rules import validate_ir
from app.plc.to_il import IrConversionError, to_il
from app.schemas import DeviceRule, IoRow
from app.spec import load_instructions

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def example():
    data = json.loads((FIXTURES / "self_hold.json").read_text(encoding="utf-8"))
    return StructuredRequirements.model_validate(data["requirements"]), Ir.model_validate(data["ir"])


def contact(signal, kind="NO"):
    return Contact(signal=signal, kind=kind)


def circuit(node, outputs=None):
    return Ir(rungs=[Rung(
        id="R1", condition=node,
        outputs=outputs if outputs is not None else [Output(kind="OUT", target="Y0")],
    )])


def check_failure(req, ir, code, **kwargs):
    before = ir.model_dump()
    result = validate_ir(ir, req.plc_config, req.io_list, **kwargs)
    assert not result.passed
    assert code in {issue.code for issue in result.errors}
    with pytest.raises(IrConversionError) as caught:
        to_il(ir, req.plc_config, req.io_list, **kwargs)
    assert caught.value.result == result
    assert str(caught.value)
    assert ir.model_dump() == before
    return result


@pytest.mark.parametrize("name", ["self_hold", "on_delay", "estop_interlock"])
def test_fixed_examples(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "expected_il.json").read_text(encoding="utf-8"))[name]
    req = StructuredRequirements.model_validate(data["requirements"])
    ir = Ir.model_validate(data["ir"])
    before = ir.model_dump()
    limits = {"T": 1} if name == "on_delay" else {}
    result = validate_ir(ir, req.plc_config, req.io_list, internal_limits=limits)
    assert result.passed, result.errors
    assert {w.code for w in result.warnings} == {"UNVERIFIED_CPU_LIMITS", "EXPERT_REVIEW_REQUIRED"}
    assert to_il(ir, req.plc_config, req.io_list, internal_limits=limits) == expected
    assert ir.model_dump() == before


def test_issue_original_nc_example(example):
    req, _ = example
    req.io_list.append(IoRow(device="X0", name="STOP_ACTIVE"))
    ir = circuit(Series(items=[
        Parallel(items=[contact("X1"), contact("Y0")]), contact("X0", "NC"),
    ]))
    assert to_il(ir, req.plc_config, req.io_list) == [
        "LD X1", "OR Y0", "ANI X0", "OUT Y0", "END",
    ]


def evaluate_node(node, values):
    if isinstance(node, Contact):
        return values[node.signal] if node.kind == "NO" else not values[node.signal]
    values = [evaluate_node(child, values) for child in node.items]
    return all(values) if node.type == "AND" else any(values)


def evaluate_il(lines, values):
    """테스트용 논리 연산만 수행한다. 실제 PLC 스캔·타이머 시뮬레이터가 아니다."""
    accumulator = False
    started = False
    blocks, saved, outputs = [], [], {}
    for line in lines:
        op, *args = line.split()
        if op in {"LD", "LDI"}:
            if started:
                blocks.append(accumulator)
            accumulator = values[args[0]] if op == "LD" else not values[args[0]]
            started = True
        elif op in {"AND", "ANI", "OR", "ORI"}:
            value = values[args[0]]
            if op in {"ANI", "ORI"}:
                value = not value
            accumulator = (accumulator and value) if op in {"AND", "ANI"} else (accumulator or value)
        elif op in {"ANB", "ORB"}:
            previous = blocks.pop()
            accumulator = (previous and accumulator) if op == "ANB" else (previous or accumulator)
        elif op == "MPS":
            saved.append(accumulator)
        elif op in {"MRD", "MPP"}:
            accumulator = saved[-1] if op == "MRD" else saved.pop()
        elif op in {"OUT", "SET", "RST"}:
            outputs[args[0]] = accumulator
            # 출력이 연산 결과를 바꾸어도 다음 출력에 원래 조건이 전달되어야 한다.
            accumulator = False
        else:
            assert op == "END"
    assert not blocks and not saved
    return outputs


def trees(leaves):
    if len(leaves) == 1:
        yield leaves[0]
        return
    for split in range(1, len(leaves)):
        for left in trees(leaves[:split]):
            for right in trees(leaves[split:]):
                for cls in (Series, Parallel):
                    yield cls(items=[left, right])


def test_all_four_contact_binary_trees_preserve_truth_tables(example):
    req, _ = example
    signals = ["X1", "X2", "Y0", "Y1"]
    req.io_list.append(IoRow(device="Y1", name="OTHER"))
    tree_count = 0
    for kinds in product(("NO", "NC"), repeat=4):
        for node in trees([contact(s, k) for s, k in zip(signals, kinds)]):
            tree_count += 1
            lines = to_il(circuit(node), req.plc_config, req.io_list)
            for bits in product((False, True), repeat=4):
                values = dict(zip(signals, bits))
                assert evaluate_il(lines, values)["Y0"] == evaluate_node(node, values)
    assert tree_count == 640


@pytest.mark.parametrize("cls", [Series, Parallel])
def test_singleton_and_three_item_groups(example, cls):
    req, _ = example
    node = cls(items=[
        contact("X1", "NC"), cls(items=[contact("X2")]), contact("Y0"),
    ])
    lines = to_il(circuit(node), req.plc_config, req.io_list)
    for bits in product((False, True), repeat=3):
        values = dict(zip(["X1", "X2", "Y0"], bits))
        assert evaluate_il(lines, values)["Y0"] == evaluate_node(node, values)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_multiple_outputs_preserve_rung_result(example, count):
    req, _ = example
    outputs = [Output(kind=kind, target=f"M{i}") for i, kind in enumerate(["OUT", "SET", "RST"][:count])]
    lines = to_il(circuit(contact("X1"), outputs), req.plc_config, req.io_list, internal_limits={"M": 3})
    expected = {
        1: ["LD X1", "OUT M0", "END"],
        2: ["LD X1", "MPS", "OUT M0", "MPP", "SET M1", "END"],
        3: ["LD X1", "MPS", "OUT M0", "MRD", "SET M1", "MPP", "RST M2", "END"],
    }
    assert lines == expected[count]
    for value in (False, True):
        assert evaluate_il(lines, {"X1": value}) == {f"M{i}": value for i in range(count)}


def test_names_and_canonical_addresses_do_not_mutate_input(example):
    req, _ = example
    req.io_list[0].device = " x01 "
    req.io_list[0].name = " Start "
    ir = circuit(Series(items=[contact(" start "), contact("x001"), contact("m010")]),
                 [Output(kind="OUT", target="motor")])
    before = ir.model_dump()
    assert to_il(ir, req.plc_config, req.io_list, internal_limits={"M": 11}) == [
        "LD X1", "AND X1", "AND M10", "OUT Y0", "END",
    ]
    assert ir.model_dump() == before


def test_q_hex_address(example):
    req, _ = example
    req.io_list.append(IoRow(device="x1f", name="LAST"))
    assert to_il(circuit(contact("LAST")), req.plc_config, req.io_list)[0] == "LD X1F"


@pytest.mark.parametrize("signal,code", [
    ("UNKNOWN", "UNKNOWN_SIGNAL"), ("X3", "UNREGISTERED_IO"),
    ("Y1", "UNREGISTERED_IO"), ("XG", "UNKNOWN_SIGNAL"),
    ("M-1", "UNKNOWN_SIGNAL"), ("M1.0", "UNKNOWN_SIGNAL"),
    ("M0\nOUT Y0", "UNKNOWN_SIGNAL"), ("SM0", "UNKNOWN_SIGNAL"),
])
def test_unknown_signals(example, signal, code):
    req, _ = example
    result = check_failure(req, circuit(contact(signal)), code)
    assert result.errors[0].rung_id == "R1"


@pytest.mark.parametrize("kind", ["M", "T", "C", "D"])
def test_internal_start_and_exclusive_end(example, kind):
    req, _ = example
    req.plc_config.device_rule = DeviceRule(**{kind: 10})
    for number in (9, 12):
        check_failure(req, circuit(contact(f"{kind}{number}")), "INTERNAL_OUT_OF_RANGE",
                      internal_limits={kind: 12})
    for number in (10, 11):
        ir = circuit(contact(f"{kind}{number}"))
        if kind == "D":
            check_failure(req, ir, "UNSUPPORTED_DEVICE", internal_limits={kind: 12})
        else:
            assert validate_ir(ir, req.plc_config, req.io_list, internal_limits={kind: 12}).passed
    check_failure(req, circuit(contact(f"{kind}10")), "INTERNAL_RANGE_REQUIRED")


@pytest.mark.parametrize("limits", [{"M": 0}, {"M": -1}, {"M": True}, {"M": 1.5}, {"Z": 10}])
def test_invalid_internal_limits(example, limits):
    req, ir = example
    check_failure(req, ir, "INVALID_INTERNAL_RANGE", internal_limits=limits)


def test_negative_start(example):
    req, ir = example
    req.plc_config.device_rule.M = -1
    check_failure(req, ir, "INVALID_INTERNAL_RANGE")


@pytest.mark.parametrize("kind,points", [("x_points", None), ("x_points", -1), ("y_points", 8193)])
def test_invalid_configured_io_points(example, kind, points):
    req, ir = example
    setattr(req.plc_config, kind, points)
    check_failure(req, ir, "INVALID_IO_POINTS")


@pytest.mark.parametrize("device", ["X20", "Y20", "X2000"])
def test_registered_io_out_of_range(example, device):
    req, ir = example
    req.io_list.append(IoRow(device=device, name="EXTRA"))
    result = validate_ir(ir, req.plc_config, req.io_list)
    assert not result.passed
    assert {e.code for e in result.errors} & {"IO_OUT_OF_RANGE", "INVALID_IO_LIST"}


@pytest.mark.parametrize("device,name,code", [
    ("X01", "EXTRA", "DUPLICATE_IO"),
    ("X3", "START", "AMBIGUOUS_SIGNAL"),
    ("X3", "Y0", "AMBIGUOUS_SIGNAL"),
    ("X3", "M0", "AMBIGUOUS_SIGNAL"),
    ("Z0", "EXTRA", "INVALID_IO_LIST"),
    ("X3", "", "INVALID_IO_LIST"),
])
def test_bad_io_registration(example, device, name, code):
    req, ir = example
    req.io_list.append(IoRow(device=device, name=name))
    check_failure(req, ir, code)


@pytest.mark.parametrize("field,value", [
    ("series", "iQ-R"), ("series", "iQ-F"), ("series", "unknown"),
    ("language", "st"), ("software", "GX Works3"), ("cpu", "unknown"),
])
def test_unsupported_configs(example, field, value):
    req, ir = example
    setattr(req.plc_config, field, value)
    check_failure(req, ir, "UNSUPPORTED_CONFIG")


@pytest.mark.parametrize("unit", [0, -1, 1, 10, 200])
def test_unsupported_timer_units(example, unit):
    req, _ = example
    req.plc_config.timer_unit_ms = unit
    check_failure(req, circuit(contact("X1"), [Output(kind="TON", target="T0", preset_ms=3000)]),
                  "UNSUPPORTED_TIMER_UNIT", internal_limits={"T": 1})


@pytest.mark.parametrize("ms,ticks", [(100, 1), (3000, 30), (3276700, 32767)])
def test_exact_timer_conversion(example, ms, ticks):
    req, _ = example
    ir = circuit(contact("X1"), [Output(kind="TON", target="T10", preset_ms=ms)])
    req.plc_config.device_rule.T = 10
    assert to_il(ir, req.plc_config, req.io_list, internal_limits={"T": 11}) == [
        "LD X1", f"OUT T10 K{ticks}", "END",
    ]


@pytest.mark.parametrize("ms", [0, 1, 99, 101, 3050, 3276800])
def test_unrepresentable_timer_presets(example, ms):
    req, _ = example
    check_failure(req, circuit(contact("X1"), [Output(kind="TON", target="T0", preset_ms=ms)]),
                  "INVALID_TIMER_PRESET", internal_limits={"T": 1})


@pytest.mark.parametrize("preset", [1, 32767])
def test_counter_conversion(example, preset):
    req, _ = example
    ir = circuit(contact("C10", "NC"), [Output(kind="CTU", target="C10", preset=preset)])
    req.plc_config.device_rule.C = 10
    assert to_il(ir, req.plc_config, req.io_list, internal_limits={"C": 11}) == [
        "LDI C10", f"OUT C10 K{preset}", "END",
    ]


@pytest.mark.parametrize("preset", [0, 32768])
def test_bad_counter_preset(example, preset):
    req, _ = example
    check_failure(req, circuit(contact("X1"), [Output(kind="CTU", target="C0", preset=preset)]),
                  "INVALID_COUNTER_PRESET", internal_limits={"C": 1})


@pytest.mark.parametrize("output", [
    Output(kind="OUT", target="X1"), Output(kind="OUT", target="D0"),
    Output(kind="OUT", target="T0"), Output(kind="SET", target="C0"),
    Output(kind="RST", target="T0"), Output(kind="TON", target="M0", preset_ms=100),
    Output(kind="CTU", target="Y0", preset=1),
])
def test_invalid_output_device(example, output):
    req, _ = example
    check_failure(req, circuit(contact("X1"), [output]), "INVALID_OUTPUT_DEVICE",
                  internal_limits={"M": 1, "T": 1, "C": 1, "D": 1})


@pytest.mark.parametrize("output", [
    Output(kind="OUT", target="Y0", preset=1),
    Output(kind="OUT", target="Y0", preset_ms=100),
    Output(kind="TON", target="T0", preset_ms=100, preset=1),
    Output(kind="CTU", target="C0", preset=1, preset_ms=100),
])
def test_irrelevant_preset_is_not_ignored(example, output):
    req, _ = example
    check_failure(req, circuit(contact("X1"), [output]), "UNEXPECTED_PRESET",
                  internal_limits={"T": 1, "C": 1})


@pytest.mark.parametrize("key", [
    "LD", "LDI", "AND", "ANI", "OR", "ORI", "ANB", "ORB",
    "OUT", "SET", "RST", "MPS", "MRD", "MPP", "END", "OUT T", "OUT C",
])
def test_every_emitted_instruction_checks_allowlist(example, monkeypatch, key):
    req, _ = example
    node = Series(items=[
        contact("X1", "NC"),
        Parallel(items=[
            contact("X2"),
            Series(items=[contact("Y0"), contact("X2", "NC")]),
            contact("X1", "NC"), contact("Y0"),
        ]),
        contact("X2"), contact("X1", "NC"),
    ])
    outputs = [
        Output(kind="OUT", target="Y0"), Output(kind="SET", target="M0"),
        Output(kind="RST", target="M1"), Output(kind="TON", target="T0", preset_ms=100),
        Output(kind="CTU", target="C0", preset=1),
    ]
    ir = circuit(node, outputs)
    instructions = load_instructions()
    modified = {**instructions, "series": {**instructions["series"],
        "Q": [op for op in instructions["series"]["Q"] if op != key]}}
    monkeypatch.setattr("app.plc.rules.load_instructions", lambda: modified)
    check_failure(req, ir, "DISALLOWED_INSTRUCTION", internal_limits={"M": 2, "T": 1, "C": 1})


def test_duplicate_rung(example):
    req, ir = example
    ir.rungs.append(ir.rungs[0].model_copy(deep=True))
    check_failure(req, ir, "DUPLICATE_RUNG")


@pytest.mark.parametrize("change", ["kind", "condition", "timer", "empty"])
def test_malformed_input_rejected_by_shared_contract(example, change):
    _, ir = example
    data = ir.model_dump()
    if change == "kind":
        data["rungs"][0]["outputs"][0]["kind"] = "MOV"
    elif change == "condition":
        data["rungs"][0]["condition"] = {"type": "AND", "items": []}
    elif change == "timer":
        data["rungs"][0]["outputs"] = [{"kind": "TON", "target": "T0"}]
    else:
        data["rungs"] = []
    with pytest.raises(ValidationError):
        Ir.model_validate(data)

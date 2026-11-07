"""실제 PLC가 아닌 개발용 스캔 모의 실행의 동작 기준."""
import json
from pathlib import Path

import pytest

from app.contracts import Ir, StructuredRequirements
from app.plc.sim import run

FIXTURES = Path(__file__).parent / "fixtures"


def load_case(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return StructuredRequirements.model_validate(data["requirements"]), Ir.model_validate(data["ir"])


def contact(signal, kind="NO"):
    return {"type": "contact", "kind": kind, "signal": signal}


def rung(rid, signal, target, kind="OUT", **preset):
    return {"id": rid, "condition": contact(signal),
            "outputs": [{"kind": kind, "target": target, **preset}]}


def test_self_hold_release_and_normally_closed_stop():
    req, ir = load_case("self_hold")
    trace = run(ir, [
        {"t_ms": 0, "set": {"START": 1, "STOP": 1}},
        {"t_ms": 50, "set": {"START": 0}},
        {"t_ms": 100, "set": {"STOP": 0}},
    ], io_list=req.io_list, until_ms=120)
    assert trace[0]["state"]["Y0"] is True
    assert trace[9]["state"]["Y0"] is True
    assert trace[10]["state"]["Y0"] is False
    assert trace[-1]["t_ms"] == 120


def test_nc_button_is_not_automatically_initialized_on():
    req, ir = load_case("self_hold")
    trace = run(ir, [{"t_ms": 0, "set": {"X1": 1}}], io_list=req.io_list)
    assert trace[0]["state"]["X2"] is False
    assert trace[0]["state"]["Y0"] is False


def test_estop_and_no_unintended_output():
    req, ir = load_case("estop_interlock")
    trace = run(ir, [
        {"t_ms": 0, "set": {"EMG": 1, "STOP": 1}},
        {"t_ms": 20, "set": {"START": 1}},
        {"t_ms": 40, "set": {"START": 0}},
        {"t_ms": 60, "set": {"EMG": 0}},
    ], io_list=req.io_list, until_ms=80)
    assert trace[0]["state"]["Y0"] is False
    assert trace[4]["state"]["Y0"] is True
    assert trace[6]["state"]["Y0"] is False
    assert all(not frame["state"]["Y1"] for frame in trace)


@pytest.mark.parametrize("delay", [3000, 5000])
def test_timer_exact_boundary_reset_and_restart(delay):
    req, ir = load_case("on_delay")
    ir.rungs[1].outputs[0].preset_ms = delay
    restart = delay + 100
    trace = run(ir, [
        {"t_ms": 0, "set": {"START": 1}},
        {"t_ms": delay + 10, "set": {"START": 0}},
        {"t_ms": restart, "set": {"START": 1}},
    ], io_list=req.io_list, until_ms=restart + delay)
    assert trace[delay // 10 - 1]["state"]["Y1"] is False
    assert trace[delay // 10]["state"]["Y1"] is True
    assert trace[delay // 10]["timers"]["T0"] == delay
    assert trace[delay // 10 + 1]["timers"]["T0"] == 0
    assert trace[delay // 10 + 1]["state"]["Y1"] is False
    assert trace[-2]["state"]["Y1"] is False
    assert trace[-1]["state"]["Y1"] is True


def test_later_rung_reads_current_scan_and_earlier_rung_reads_previous_scan():
    req, _ = load_case("self_hold")
    ir = Ir.model_validate({"rungs": [
        rung("R1", "M0", "Y0"), rung("R2", "X1", "M0"),
        rung("R3", "M0", "M1"),
    ]})
    trace = run(ir, [{"t_ms": 0, "set": {"X1": 1}}], io_list=req.io_list, until_ms=10)
    assert trace[0]["state"]["Y0"] is False
    assert trace[0]["state"]["M1"] is True
    assert trace[1]["state"]["Y0"] is True


def test_set_rst_latch_and_rung_order():
    req, _ = load_case("self_hold")
    ir = Ir.model_validate({"rungs": [
        rung("R1", "X1", "M0", "SET"), rung("R2", "X2", "M0", "RST"),
        rung("R3", "M0", "Y0"),
    ]})
    trace = run(ir, [
        {"t_ms": 0, "set": {"X1": 1}},
        {"t_ms": 10, "set": {"X1": 0}},
        {"t_ms": 20, "set": {"X1": 1, "X2": 1}},
    ], io_list=req.io_list)
    assert [frame["state"]["Y0"] for frame in trace] == [True, True, False]


def test_ctu_counts_rising_edges_not_held_input_and_keeps_count_when_off():
    req, _ = load_case("self_hold")
    ir = Ir.model_validate({"rungs": [
        rung("R1", "X1", "C0", "CTU", preset=2), rung("R2", "C0", "Y0"),
    ]})
    trace = run(ir, [
        {"t_ms": 0, "set": {"X1": 1}}, {"t_ms": 20, "set": {"X1": 0}},
        {"t_ms": 30, "set": {"X1": 1}}, {"t_ms": 40, "set": {"X1": 0}},
    ], io_list=req.io_list)
    assert [f["counters"]["C0"] for f in trace] == [1, 1, 1, 2, 2]
    assert [f["state"]["Y0"] for f in trace] == [False, False, False, True, True]


def test_nested_no_nc_and_or_and_multiple_outputs():
    req, _ = load_case("self_hold")
    ir = Ir.model_validate({"rungs": [{
        "id": "R1",
        "condition": {"type": "OR", "items": [
            {"type": "AND", "items": [contact("X1"), contact("X2", "NC")]},
            contact("M0"),
        ]},
        "outputs": [{"kind": "OUT", "target": "Y0"}, {"kind": "OUT", "target": "M0"}],
    }]})
    trace = run(ir, [
        {"t_ms": 0, "set": {"X1": 1, "X2": 0}},
        {"t_ms": 10, "set": {"X1": 0, "X2": 1}},
    ], io_list=req.io_list)
    assert all(f["state"]["Y0"] and f["state"]["M0"] for f in trace)


def test_aliases_addresses_and_no_mutation_or_state_leak():
    req, ir = load_case("self_hold")
    original = ir.model_dump()
    ir.rungs[0].outputs[0].target = " motor "
    steps = [{"t_ms": 0, "set": {" start ": True, "x02": 1}}]
    before = json.dumps(steps)
    first = run(ir, steps, io_list=req.io_list)
    assert first[0]["state"]["Y0"] is True
    assert json.dumps(steps) == before
    assert ir.rungs[0].outputs[0].target == " motor "
    assert not run(ir, [], io_list=req.io_list)[0]["state"]["Y0"]
    first[0]["state"]["Y0"] = False
    assert run(Ir.model_validate(original), steps, io_list=req.io_list)[0]["state"]["Y0"]


@pytest.mark.parametrize("steps", [
    [{"t_ms": -10, "set": {"X1": 1}}],
    [{"t_ms": 1, "set": {"X1": 1}}],
    [{"t_ms": True, "set": {"X1": 1}}],
    [{"t_ms": 10, "set": {}}, {"t_ms": 0, "set": {}}],
    [{"t_ms": 0, "set": {}}, {"t_ms": 0, "set": {}}],
    [{"t_ms": 0, "set": {"X1": 2}}],
    [{"t_ms": 0, "set": {"X1": "1"}}],
    [{"t_ms": 0, "set": {"Y0": 1}}],
    [{"t_ms": 0, "set": {"UNKNOWN": 1}}],
    [{"t_ms": 0, "set": {"X1": 1, "START": 0}}],
    [{"t_ms": 0, "set": {}, "typo": 1}],
])
def test_invalid_steps_are_explicit_errors(steps):
    req, ir = load_case("self_hold")
    with pytest.raises(ValueError):
        run(ir, steps, io_list=req.io_list)


@pytest.mark.parametrize("options", [
    {"scan_ms": 0}, {"scan_ms": True}, {"scan_ms": 1.5},
    {"until_ms": -1}, {"until_ms": 1}, {"until_ms": 1_000_000},
])
def test_invalid_scan_settings(options):
    req, ir = load_case("self_hold")
    with pytest.raises(ValueError):
        run(ir, [], io_list=req.io_list, **options)


def test_event_after_end_is_not_silently_discarded():
    req, ir = load_case("self_hold")
    with pytest.raises(ValueError):
        run(ir, [{"t_ms": 20, "set": {"X1": 1}}], io_list=req.io_list, until_ms=10)


def test_unknown_ir_signal_is_not_assumed_off():
    req, ir = load_case("self_hold")
    ir.rungs[0].condition.items[0].items[0].signal = "MISSING"
    with pytest.raises(ValueError):
        run(ir, [], io_list=req.io_list)


def test_timer_interrupted_before_completion_does_not_accumulate_across_off():
    req, ir = load_case("on_delay")
    trace = run(ir, [
        {"t_ms": 0, "set": {"START": 1}},
        {"t_ms": 2000, "set": {"START": 0}},
        {"t_ms": 2100, "set": {"START": 1}},
    ], io_list=req.io_list, until_ms=5100)
    assert trace[200]["timers"]["T0"] == 0
    assert trace[509]["state"]["Y1"] is False
    assert trace[510]["state"]["Y1"] is True


def test_repeated_counter_run_resets_count_and_trace_frames_are_independent():
    req, _ = load_case("self_hold")
    ir = Ir.model_validate({"rungs": [rung("R1", "X1", "C0", "CTU", preset=2)]})
    steps = [{"t_ms": 0, "set": {"X1": 1}}, {"t_ms": 10, "set": {"X1": 0}},
             {"t_ms": 20, "set": {"X1": 1}}]
    trace = run(ir, steps, io_list=req.io_list)
    assert trace[0]["counters"]["C0"] == 1
    assert trace[-1]["counters"]["C0"] == 2
    trace[-1]["counters"]["C0"] = 99
    assert trace[0]["counters"]["C0"] == 1
    assert run(ir, [], io_list=req.io_list)[0]["counters"]["C0"] == 0

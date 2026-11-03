"""자동 지시문 생성: 손으로 쓴 지시와 같은 결과가 나오는지, 모호하면 만들지 않는지 검사한다."""
import json

import pytest

from app.contracts import Condition, CounterSpec
from app.plc.design import DesignError, PREFIX, design_circuit
from app.plc.directives import with_auto_directives
from test_design import directives, load_case, replace_directives


@pytest.mark.parametrize("name", ["self_hold", "on_delay", "estop_interlock"])
def test_auto_matches_hand_written_directives(name):
    req, expected = load_case(name)
    hand = directives(req)
    replace_directives(req, [])
    auto, skipped = with_auto_directives(req)
    assert skipped == {}
    assert directives(auto) == hand
    assert design_circuit(auto).il == expected
    assert req.assumptions == [a for a in req.assumptions if not a.startswith(PREFIX)]


def test_explicit_directive_is_never_overwritten():
    req, _ = load_case("self_hold")
    hand = directives(req)
    auto, skipped = with_auto_directives(req)
    assert directives(auto) == hand and skipped == {}


def stripped():
    req, _ = load_case("self_hold")
    replace_directives(req, [])
    return req


def test_start_button_without_hold_cue_is_ambiguous():
    req = stripped()
    req.conditions[0].text = "START를 누르면 MOTOR가 켜진다."
    auto, skipped = with_auto_directives(req)
    assert "C1" in skipped and "C2" not in skipped
    with pytest.raises(DesignError, match="자동 지시 생략|설계 지시가 없어서"):
        design_circuit(auto)


def test_while_pressed_is_direct():
    req = stripped()
    req.conditions[0].text = "START를 누르는 동안 MOTOR가 켜진다."
    auto, skipped = with_auto_directives(req)
    assert skipped == {}
    assert [d["mode"] for d in directives(auto)] == ["direct", "block"]
    assert design_circuit(auto).il[-1] == "END"


def test_multiple_inputs_need_join_cue():
    req = stripped()
    req.io_list.append(type(req.io_list[0])(device="X3", name="START2", kind="푸시버튼 NO", desc=""))
    req.conditions[0].signals = ["START", "START2", "MOTOR"]
    req.conditions[0].text = "START와 START2를 누르면 MOTOR가 켜지고 유지된다."
    assert "C1" in with_auto_directives(req)[1]
    req.conditions[0].text = "START 또는 START2를 누르면 MOTOR가 켜지고 유지된다."
    auto, skipped = with_auto_directives(req)
    assert "C1" not in skipped
    assert directives(auto)[0]["join"] == "any"


def test_stop_without_cue_is_skipped_and_reason_listed():
    req = stripped()
    req.conditions[1].text = "STOP 버튼이 있다."
    _, skipped = with_auto_directives(req)
    assert "C2" in skipped


def test_unknown_signal_is_skipped():
    req = stripped()
    req.conditions[0].signals = ["START", "NOPE"]
    assert "NOPE" in with_auto_directives(req)[1]["C1"]


def test_counter_condition():
    req = stripped()
    req.counters.append(CounterSpec(name="C0", preset=5, purpose="횟수"))
    req.conditions[0].text = "START를 5번 카운트하면 MOTOR가 켜진다."
    auto, skipped = with_auto_directives(req)
    assert skipped == {}
    assert directives(auto)[0] == {
        "condition_id": "C1", "mode": "count", "inputs": [{"signal": "START", "active": "on"}],
        "join": "all", "outputs": ["MOTOR"], "counter": "C0", "reset": "none",
    }


def test_safety_not_used_is_skipped():
    req = stripped()
    req.conditions.append(Condition(id="C9", type="safety", text="비상정지", signals=["STOP"]))
    assert "C9" in with_auto_directives(req)[1]


def test_input_not_mutated():
    req = stripped()
    before = req.model_dump()
    with_auto_directives(req)
    assert req.model_dump() == before


@pytest.mark.parametrize("name", ["self_hold", "on_delay", "estop_interlock"])
def test_pipeline_without_any_directive(client, name):
    from app import db
    from app.agents import orchestrator
    from app.agents.schemas import LlmAnalysis

    req, expected = load_case(name)
    replace_directives(req, [])
    project = db.create_project("자동 지시 시험", {
        "plc_config": req.plc_config.model_dump(),
        "io_list": [row.model_dump() for row in req.io_list],
        "conditions": [c.model_dump() for c in req.conditions],
    })
    job, _ = orchestrator.start_job(project["id"])
    orchestrator.submit_requirements(job["id"], LlmAnalysis(
        conditions=req.conditions, timers=req.timers, counters=req.counters, assumptions=req.assumptions,
    ))
    result = orchestrator.generate_design(job["id"])
    assert result["job"]["state"] == "DESIGNING", result.get("reason")
    assert result["design"]["il"] == expected
    assert any(a.startswith(PREFIX) for a in result["design"]["assumptions"])


def test_runner_designs_automatically_after_analysis(client, monkeypatch):
    from app import db
    from app.agents import orchestrator, runner
    from app.agents.schemas import LlmAnalysis

    req, expected = load_case("self_hold")
    replace_directives(req, [])
    project = db.create_project("자동 설계", {
        "plc_config": req.plc_config.model_dump(),
        "io_list": [row.model_dump() for row in req.io_list],
        "conditions": [c.model_dump() for c in req.conditions],
    })
    job, _ = orchestrator.start_job(project["id"])
    monkeypatch.setattr(runner, "run_directline", lambda job_id: orchestrator.submit_requirements(
        job_id, LlmAnalysis(conditions=req.conditions)))
    runner._run(job["id"], "directline")
    events = db.list_events(job["id"])
    design = next(e for e in events if e["kind"] == "design")
    assert design["data"]["il"] == expected
    assert db.get_job(job["id"])["state"] == "DESIGNING"

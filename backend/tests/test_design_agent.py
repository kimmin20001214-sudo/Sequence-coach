"""설계 에이전트가 낸 회로(IR)를 코드가 검사·변환·저장하는지 확인한다."""
import json
from pathlib import Path

import pytest

from app import db
from app.agents import orchestrator
from app.contracts import StructuredRequirements
from app.plc.design_check import check_design
from test_agents import KEY, make_project

CASES = json.loads((Path(__file__).parent / "fixtures" / "ir_cases.json").read_text(encoding="utf-8"))


def load(name):
    case = json.loads(json.dumps(CASES[name]))
    return StructuredRequirements.model_validate(case["requirements"]), case["ir"], case["expected_il"]


@pytest.mark.parametrize("name", list(CASES))
def test_good_ir_passes_and_converts(name):
    req, ir, expected = load(name)
    from app.contracts import Ir

    result, problems = check_design(req, Ir.model_validate(ir))
    assert problems == [] and result.il == expected
    assert result.io_used and result.explanation


def test_missing_condition_coverage_is_rejected():
    from app.contracts import Ir

    req, ir, _ = load("self_hold")
    ir["rungs"][0]["covers"] = []
    result, problems = check_design(req, Ir.model_validate(ir))
    assert result is None and any("UNMET_CONDITION" in p for p in problems)


def test_estop_missing_is_rejected():
    from app.contracts import Ir

    req, ir, _ = load("estop_interlock")
    ir["rungs"][0]["condition"] = {"type": "contact", "kind": "NO", "signal": "X1"}
    result, problems = check_design(req, Ir.model_validate(ir))
    assert result is None and any("ESTOP_MISSING" in p for p in problems)


def test_no_button_estop_needs_b_contact():
    from app.contracts import Ir

    req, ir, _ = load("estop_interlock")
    estop = req.plc_config.emergency_stop.device
    for row in req.io_list:
        if row.device == estop:
            row.kind = "푸시버튼 NO"

    names = {r.device for r in req.io_list if r.device == estop} | {r.name for r in req.io_list if r.device == estop}

    def with_kind(node, kind):
        if node.get("type") == "contact" and node["signal"] in names:
            node["kind"] = kind
        for item in node.get("items", []):
            with_kind(item, kind)

    for rung in ir["rungs"]:
        with_kind(rung["condition"], "NO")
    _, problems = check_design(req, Ir.model_validate(ir))
    assert any("ESTOP_MISSING" in p and "b접점" in p for p in problems)
    for rung in ir["rungs"]:
        with_kind(rung["condition"], "NC")
    _, problems = check_design(req, Ir.model_validate(ir))
    assert not any("ESTOP_MISSING" in p for p in problems)


def test_non_q_series_is_rejected():
    from app.contracts import Ir

    req, ir, _ = load("self_hold")
    req.plc_config.series = "iQ-R"
    result, problems = check_design(req, Ir.model_validate(ir))
    assert result is None and "Q시리즈" in problems[0]


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")


def to_designing(client, ir_case="self_hold"):
    pid = make_project(client)
    job, _ = orchestrator.start_job(pid)
    req, _, _ = load(ir_case)
    db.update_job(job["id"], "DESIGNING")
    db.add_event(job["id"], "DESIGNING", "requirements", req.model_dump())
    return job["id"]


def test_submit_design_stores_good_ir_and_rejects_bad(client):
    job_id = to_designing(client)
    _, ir, expected = load("self_hold")
    bad = client.post(f"/agent/jobs/{job_id}/design", headers=KEY, json={"ir": {"version": 1, "rungs": []}}).json()
    assert bad["ok"] is False and bad["errors"] and bad["state"] == "DESIGNING"
    check = client.post(f"/agent/jobs/{job_id}/design-check", headers=KEY, json={"ir": ir}).json()
    assert check == {"ok": True, "errors": [], "il": expected}
    good = client.post(f"/agent/jobs/{job_id}/design", headers=KEY, json={"ir": ir}).json()
    assert good["ok"] is True and good["design"]["il"] == expected
    kinds = [e["kind"] for e in db.list_events(job_id)]
    assert "design_rejected" in kinds
    assert kinds[kinds.index("design"):][:3] == ["design", "verifying", "verification"]
    assert good["state"] in {"COMPLETED", "ESCALATED"}


def test_five_rejections_fail_the_job(client):
    job_id = to_designing(client)
    for _ in range(5):
        r = client.post(f"/agent/jobs/{job_id}/design", headers=KEY, json={"ir": {"version": 1, "rungs": []}}).json()
    assert r["state"] == "FAILED" and r["ok"] is False


def test_get_design_input_needs_designing(client):
    job_id = to_designing(client)
    r = client.get(f"/agent/jobs/{job_id}/design-input", headers=KEY).json()
    assert r["requirements"]["conditions"]
    db.update_job(job_id, "FAILED")
    assert client.get(f"/agent/jobs/{job_id}/design-input", headers=KEY).status_code == 409


def _design_with_check(client, check):
    from app.contracts import Check
    pid = make_project(client)
    job, _ = orchestrator.start_job(pid)
    req, ir, _ = load("self_hold")
    req.conditions[0].check = check
    req.conditions[1].check = Check(pattern="stop_priority", stop="STOP", outputs=["MOTOR"])
    db.update_job(job["id"], "DESIGNING")
    db.add_event(job["id"], "DESIGNING", "requirements", req.model_dump())
    res = client.post(f"/agent/jobs/{job['id']}/design", headers=KEY, json={"ir": ir}).json()
    ev = next(e for e in db.list_events(job["id"]) if e["kind"] == "verification")
    return res, ev["data"]


def test_verified_design_completes_with_condition_table(client):
    from app.contracts import Check
    res, v = _design_with_check(client, Check(pattern="self_hold", start="START", stop="STOP", output="MOTOR"))
    assert res["state"] == "COMPLETED" and v["passed"] is True
    assert v["conditions"][0]["status"] == "PASS" and "전문가" in v["notice"]


def test_failed_verification_escalates_with_reason(client):
    from app.contracts import Check
    res, v = _design_with_check(client, Check(pattern="on_delay", trigger="START", output="MOTOR", delay_ms=5000))
    assert res["state"] == "ESCALATED" and v["passed"] is False
    assert v["conditions"][0]["status"] in {"FAIL", "UNVERIFIED"}


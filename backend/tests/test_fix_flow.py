"""검증 실패 → FIXING → 수정 제출 → 재검증 흐름(구현6 연결)을 확인한다."""
import json

import pytest

from app import db
from app.agents import orchestrator
from app.contracts import Check
from test_agents import KEY, make_project
from test_design_agent import load


@pytest.fixture(autouse=True)
def fix_on(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("FIX_ENABLED", "1")


def broken_job(client):
    """자기유지 접점이 빠진 회로를 제출해 검증 실패(FIXING) 상태까지 만든다."""
    pid = make_project(client)
    job, _ = orchestrator.start_job(pid)
    req, good, _ = load("self_hold")
    req.conditions[0].check = Check(pattern="self_hold", start="START", stop="STOP", output="MOTOR")
    req.conditions[1].check = Check(pattern="stop_priority", stop="STOP", outputs=["MOTOR"])
    db.update_job(job["id"], "DESIGNING")
    db.add_event(job["id"], "DESIGNING", "requirements", req.model_dump())
    bad = json.loads(json.dumps(good))
    bad["rungs"][0]["condition"] = {"type": "AND", "items": [
        {"type": "contact", "kind": "NO", "signal": "X1"},
        {"type": "contact", "kind": "NO", "signal": "X2"},
    ]}
    res = client.post(f"/agent/jobs/{job['id']}/design", headers=KEY, json={"ir": bad}).json()
    return job["id"], bad, good, res


def test_failed_verification_goes_to_fixing_and_exposes_request(client):
    job_id, bad, _, res = broken_job(client)
    assert res["state"] == "FIXING" and res["iteration"] == 1
    r = client.get(f"/agent/jobs/{job_id}/fix-input", headers=KEY).json()
    fr = r["fix_request"]
    assert fr["failed_conditions"][0]["id"] == "C1" and fr["ir"] == bad
    assert fr["plc_series"] == "Q" and fr["similar_cases"] == []


def test_good_fix_completes_and_saves_knowledge(client):
    job_id, _, good, _ = broken_job(client)
    r = client.post(f"/agent/jobs/{job_id}/fix", headers=KEY, json={"ir": good, "reason": "자기유지 접점 추가"}).json()
    assert r["ok"] is True and r["state"] == "COMPLETED" and r["diff"]["changed"]
    events = db.list_events(job_id)
    kinds = [e["kind"] for e in events]
    assert "fix_applied" in kinds and "knowledge_skipped" not in kinds
    last_design = [e for e in events if e["kind"] == "design"][-1]["data"]
    assert last_design["il"] == ["LD X1", "OR Y0", "AND X2", "OUT Y0", "END"]
    assert [e for e in events if e["kind"] == "verification"][-1]["data"]["passed"] is True
    from app.plc.error_knowledge import build_signature, find_similar
    cases = find_similar("Q", build_signature("Q", "sequence", "UNMET_CONDITION"), [])
    assert len(cases) == 1 and cases[0]["verified"] == 1
    assert client.get(f"/agent/jobs/{job_id}/fix-input", headers=KEY).status_code == 409


def test_rejected_fix_retries_then_escalates(client):
    job_id, bad, _, _ = broken_job(client)
    db.update_job(job_id, "FIXING", 1)
    states = []
    for _ in range(6):
        r = client.post(f"/agent/jobs/{job_id}/fix", headers=KEY, json={"ir": bad})
        if r.status_code != 200:
            break
        body = r.json()
        assert body["ok"] is False and body["errors"]
        states.append((body["state"], body["iteration"]))
        if body["state"] == "ESCALATED":
            break
    assert states[-1][0] == "ESCALATED" and states[0] == ("FIXING", 2)
    events = db.list_events(job_id)
    assert [e for e in events if e["kind"] == "escalated"][-1]["data"]["reason"]
    assert any(e["kind"] == "fix_rejected" for e in events)


def test_fix_that_breaks_another_condition_is_rejected(client):
    job_id, _, good, _ = broken_job(client)
    worse = json.loads(json.dumps(good))
    worse["rungs"][0]["condition"] = {"type": "contact", "kind": "NO", "signal": "X1"}
    r = client.post(f"/agent/jobs/{job_id}/fix", headers=KEY, json={"ir": worse}).json()
    assert r["ok"] is False and r["state"] == "FIXING" and r["iteration"] == 2
    assert db.list_events(job_id)[-1]["kind"] != "knowledge_skipped"


def test_fix_off_escalates_immediately(client, monkeypatch):
    monkeypatch.delenv("FIX_ENABLED")
    _, _, _, res = broken_job(client)
    assert res["state"] == "ESCALATED"


def test_fail_job_in_fixing_escalates(client):
    job_id, _, _, _ = broken_job(client)
    assert orchestrator.fail_job(job_id, "응답 없음")["state"] == "ESCALATED"


def test_runner_calls_fix_agent_until_done(client, monkeypatch):
    from app.agents import runner

    job_id, bad, good, _ = broken_job(client)
    calls = []

    def fake_agent(jid, design=False, fix=False):
        calls.append(fix)
        if fix:
            orchestrator.submit_fix(jid, bad if len(calls) < 3 else good)

    monkeypatch.setattr(runner, "run_directline", fake_agent)
    runner._run(job_id, "directline")
    assert db.get_job(job_id)["state"] == "COMPLETED" and calls == [False, True, True]


def test_run_directline_fix_polls_until_submitted(client, monkeypatch):
    from app.agents import runner

    job_id, bad, good, _ = broken_job(client)
    monkeypatch.setenv("COPILOT_DIRECTLINE_SECRET", "s")
    sent = []

    def fake_http(method, url, token=None, body=None):
        if url.endswith("/conversations"):
            return {"conversationId": "c", "token": "t"}
        if method == "POST":
            sent.append(body["text"])
            return {}
        orchestrator.submit_fix(job_id, good)
        return {"activities": []}

    monkeypatch.setattr(runner, "_http", fake_http)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    runner.run_directline(job_id, fix=True)
    assert "[수정 시작]" in sent[0] and db.get_job(job_id)["state"] == "COMPLETED"


def test_run_waits_for_verifying_before_fix(client, monkeypatch):
    from app.agents import runner

    job_id, bad, good, _ = broken_job(client)
    seq = iter(["VERIFYING", "VERIFYING", "FIXING", "FIXING", "FIXING"])
    states = []
    monkeypatch.setattr(runner, "_state", lambda j: states.append(1) or next(seq, "FIXING"))
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    runner._wait_verified(job_id)
    assert len(states) == 3


def test_mcp_exposes_fix_tools(client):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    names = [t["name"] for t in client.post("/mcp", headers=KEY, json=body).json()["result"]["tools"]]
    assert {"getFixInput", "submitFix"} <= set(names)

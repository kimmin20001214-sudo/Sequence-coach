import pytest

from app import db
from app.agents import orchestrator
from conftest import valid_project

KEY = {"X-API-Key": "test-key"}
IO = [
    {"device": "X0", "name": "EMG", "kind": "푸시버튼 NC (b접점)", "desc": ""},
    {"device": "X1", "name": "START", "kind": "푸시버튼 NO", "desc": ""},
    {"device": "Y0", "name": "MOTOR", "kind": "모터", "desc": ""},
]


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")


def make_project(client, conditions=None):
    p = valid_project(series="Q", cpu="Q06HCPU", software="GX Works2")
    p["io_list"] = IO
    p["conditions"] = [{"id": "", "text": t, "must_pass": True} for t in (conditions or ["START 누르면 MOTOR ON"])]
    r = client.post("/projects", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def start(client, pid):
    r = client.post(f"/agent/projects/{pid}/jobs", headers=KEY)
    assert r.status_code == 201, r.text
    return r.json()


def test_api_key_required(client, monkeypatch):
    pid = make_project(client)
    assert client.post(f"/agent/projects/{pid}/jobs").status_code == 401
    assert client.post(f"/agent/projects/{pid}/jobs", headers={"X-API-Key": "wrong"}).status_code == 401
    monkeypatch.delenv("AGENT_API_KEY")
    assert client.post(f"/agent/projects/{pid}/jobs", headers=KEY).status_code == 503


def test_start_job_returns_input_and_moves_to_analyzing(client):
    pid = make_project(client)
    body = start(client, pid)
    assert body["job"]["state"] == "ANALYZING"
    assert body["project"]["io_list"][0]["device"] == "X0"
    assert body["project"]["conditions"][0]["text"] == "START 누르면 MOTOR ON"
    assert client.post("/agent/projects/nope/jobs", headers=KEY).status_code == 404


def test_two_conditions_structured_and_moves_to_designing(client):
    pid = make_project(client, ["START 누르면 MOTOR ON", "EMG 누르면 모두 OFF"])
    job = start(client, pid)["job"]["job_id"]
    r = client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json={"conditions": [
        {"type": "sequence", "text": "START 누르면 MOTOR ON 유지", "signals": ["START", "MOTOR"]},
        {"type": "safety", "text": "EMG 누르면 모두 OFF", "signals": ["X0"]},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "DESIGNING"
    assert [e["state"] for e in body["events"]] == ["INPUT_VALIDATED", "ANALYZING", "DESIGNING"]
    assert [c["id"] for c in body["events"][-1]["data"]["conditions"]] == ["C1", "C2"]
    assert client.get(f"/projects/{pid}/status").json()["state"] == "DESIGNING"
    assert client.get(f"/projects/{pid}").json()["status"] == "DESIGNING"


def test_emergency_stop_condition_added_automatically(client):
    job = start(client, make_project(client))["job"]["job_id"]
    body = client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json={"conditions": [
        {"type": "sequence", "text": "START 누르면 MOTOR ON", "signals": ["X1", "Y0"]}]}).json()
    last = body["events"][-1]["data"]["conditions"][-1]
    assert last["type"] == "safety" and last["must_pass"] and "X0" in last["text"]


def test_unknown_signal_and_agent_questions_need_input(client):
    job = start(client, make_project(client))["job"]["job_id"]
    body = client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json={
        "conditions": [{"type": "sequence", "text": "PUMP 켜기", "signals": ["PUMP"]}],
        "questions": ["몇 초 동안 켜 둘까요?"]}).json()
    assert body["state"] == "NEEDS_INPUT"
    assert any("PUMP" in q for q in body["questions"]) and "몇 초 동안 켜 둘까요?" in body["questions"]


def test_bad_shape_rejected_and_wrong_state_conflict(client):
    job = start(client, make_project(client))["job"]["job_id"]
    bad = client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json={"conditions": [{"type": "nope", "text": "x"}]})
    assert bad.status_code == 422
    ok = {"conditions": [{"type": "sequence", "text": "x", "signals": ["START"]}]}
    assert client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json=ok).status_code == 200
    assert client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json=ok).status_code == 409
    assert client.post("/agent/jobs/nope/requirements", headers=KEY, json=ok).status_code == 404


def test_status_before_start_and_unknown_project(client):
    pid = make_project(client)
    assert client.get(f"/projects/{pid}/status").json()["state"] == "INPUT_VALIDATED"
    assert client.get("/projects/nope/status").status_code == 404


def test_verification_endpoint_and_escalation(client):
    job = db.create_job("p1", "VERIFYING", max_iter=2)
    states = []
    for _ in range(3):
        r = client.post(f"/agent/jobs/{job['id']}/verification", headers=KEY, json={"passed": False})
        assert r.status_code == 200
        states.append((r.json()["state"], r.json()["iteration"]))
        if r.json()["state"] == "FIXING":
            db.update_job(job["id"], "VERIFYING")
    assert states == [("FIXING", 1), ("FIXING", 2), ("ESCALATED", 2)]
    assert client.post(f"/agent/jobs/{job['id']}/verification", headers=KEY, json={"passed": True}).status_code == 409


def test_verification_pass(client):
    job = db.create_job("p1", "VERIFYING")
    assert orchestrator.report_verification(job["id"], passed=True)["state"] == "COMPLETED"


def test_agent_spec_is_openapi_30_with_tools_only(client):
    spec = client.get("/agent-spec.json").json()
    assert spec["openapi"].startswith("3.0")
    assert set(spec["paths"]) == {"/agent/projects/{project_id}/jobs", "/agent/projects/{project_id}/status",
                                  "/agent/jobs/{job_id}", "/agent/jobs/{job_id}/requirements",
                                  "/agent/jobs/{job_id}/verification", "/agent/jobs/{job_id}/design",
                                  "/agent/jobs/{job_id}/design-input", "/agent/jobs/{job_id}/design-check",
                                  "/agent/jobs/{job_id}/fix-input", "/agent/jobs/{job_id}/fix"}
    ids = {op["operationId"] for p in spec["paths"].values() for op in p.values()}
    assert ids == {"startJob", "getStatus", "getJob", "submitRequirements", "reportVerification", "submitDesign",
                   "getDesignInput", "validateIr", "getFixInput", "submitFix"}
    assert "null" not in str(spec)

"""설계 저장·실패 상태·REST/MCP 연결의 통합 검사."""
import json

import pytest

from app import db
from app.agents import orchestrator
from app.agents.schemas import LlmAnalysis
from app.plc import design
from test_agents import KEY
from test_design import load_case
from test_mcp import rpc


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")


def ready_job(client, name="self_hold"):
    req, _ = load_case(name)
    project = db.create_project("설계 시험", {
        "plc_config": req.plc_config.model_dump(),
        "io_list": [row.model_dump() for row in req.io_list],
        "conditions": [c.model_dump() for c in req.conditions],
    })
    job, _ = orchestrator.start_job(project["id"])
    orchestrator.submit_requirements(job["id"], LlmAnalysis(
        conditions=req.conditions, timers=req.timers, counters=req.counters, assumptions=req.assumptions,
    ))
    return job["id"], req


@pytest.mark.parametrize("name", ["self_hold", "on_delay", "estop_interlock"])
def test_orchestrator_saved_result_state_and_idempotency(client, name, monkeypatch):
    job_id, req = ready_job(client, name)
    body = orchestrator.generate_design(job_id)
    assert body["job"]["state"] == "DESIGNING"
    assert body["design"]["il"] == design.design_circuit(req).il
    events = db.list_events(job_id)
    assert events[-1]["kind"] == "design"
    assert events[-1]["data"] == body["design"]
    assert db.get_project(body["job"]["project_id"])["status"] == "DESIGNING"

    def no_regeneration(req):
        pytest.fail("저장된 초안을 재생성하면 안 됩니다.")

    monkeypatch.setattr(design, "design_circuit", no_regeneration)
    assert orchestrator.generate_design(job_id) == body
    assert db.list_events(job_id) == events


def test_latest_requirements_used_and_failure_recorded(client, monkeypatch):
    job_id, req = ready_job(client)
    req.questions = ["정지 방식?"]
    db.add_event(job_id, "DESIGNING", "requirements", req.model_dump())
    calls = []
    fail = orchestrator.fail_job

    def tracked_fail(*args):
        calls.append(args)
        return fail(*args)

    monkeypatch.setattr(orchestrator, "fail_job", tracked_fail)
    body = orchestrator.generate_design(job_id)
    assert body["job"]["state"] == "FAILED" and body["design"] is None
    assert "질문" in body["reason"]
    assert calls == [(job_id, body["reason"])]
    events = db.list_events(job_id)
    assert [e["kind"] for e in events[-2:]] == ["design_error", "error"]
    assert events[-2]["data"]["reason"] == body["reason"]
    assert db.get_project(body["job"]["project_id"])["status"] == "FAILED"
    assert not any(e["kind"] == "design" for e in events)


@pytest.mark.parametrize("kind,data", [
    ("requirements", {}), ("requirements", []), ("requirements", {"conditions": "bad"}),
    ("design", {}), ("design", {"ir": None}),
])
def test_malformed_stored_contract_is_failure(client, kind, data):
    job_id, _ = ready_job(client)
    db.add_event(job_id, "DESIGNING", kind, data)
    result = orchestrator.generate_design(job_id)
    assert result["job"]["state"] == "FAILED" and result["design"] is None
    assert "계약 형식" in result["reason"]
    assert db.list_events(job_id)[-2]["kind"] == "design_error"


def test_missing_requirements_and_unknown_job(client):
    job = db.create_job("none", "DESIGNING")
    assert orchestrator.generate_design(job["id"])["job"]["state"] == "FAILED"
    with pytest.raises(KeyError):
        orchestrator.generate_design("missing")


@pytest.mark.parametrize("state", ["ANALYZING", "VERIFYING", "FAILED", "COMPLETED", "NEEDS_INPUT"])
def test_wrong_state_never_changes_job(client, state):
    job = db.create_job("none", state)
    with pytest.raises(orchestrator.InvalidTransition):
        orchestrator.generate_design(job["id"])
    assert db.get_job(job["id"]) == job
    assert db.list_events(job["id"]) == []


def test_rest_auth_success_failure_conflict_not_found(client):
    job_id, req = ready_job(client)
    path = f"/agent/jobs/{job_id}/design"
    assert client.post(path).status_code == 401
    assert client.post(path, headers={"X-API-Key": "wrong"}).status_code == 401
    response = client.post(path, headers=KEY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "DESIGNING" and body["design"]["il"][-1] == "END"
    assert client.post(path, headers=KEY).json()["design"] == body["design"]
    job_id, req = ready_job(client)
    req.assumptions = []
    req.conditions[0].text = "START를 누르면 MOTOR가 켜진다."
    db.add_event(job_id, "DESIGNING", "requirements", req.model_dump())
    failed = client.post(f"/agent/jobs/{job_id}/design", headers=KEY)
    assert failed.status_code == 200
    assert failed.json()["state"] == "FAILED" and failed.json()["design"] is None
    assert "설계 지시" in failed.json()["reason"]
    assert client.post(f"/agent/jobs/{job_id}/design", headers=KEY).status_code == 409
    assert client.post("/agent/jobs/missing/design", headers=KEY).status_code == 404


def test_mcp_auth_schema_success_failure(client):
    job_id, req = ready_job(client)
    params = {"name": "generateDesign", "arguments": {"job_id": job_id}}
    assert rpc(client, "tools/call", params, headers={}).status_code == 401
    assert rpc(client, "tools/call", params, headers={"X-API-Key": "wrong"}).status_code == 401
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    tool = next(t for t in tools if t["name"] == "generateDesign")
    assert set(tool["inputSchema"]["properties"]) == {"job_id"}
    assert tool["inputSchema"]["required"] == ["job_id"]
    result = rpc(client, "tools/call", params).json()["result"]
    assert not result["isError"]
    assert json.loads(result["content"][0]["text"])["state"] == "DESIGNING"
    job_id, req = ready_job(client)
    req.questions = ["확인 필요"]
    db.add_event(job_id, "DESIGNING", "requirements", req.model_dump())
    params["arguments"]["job_id"] = job_id
    result = rpc(client, "tools/call", params).json()["result"]
    assert result["isError"]
    data = json.loads(result["content"][0]["text"])
    assert data["state"] == "FAILED" and data["design"] is None
    assert "질문" in data["reason"]


@pytest.mark.parametrize("arguments", [{}, {"job_id": 3}, {"job_id": ""}, {"job_id": "x", "extra": 1}])
def test_mcp_invalid_arguments(client, arguments):
    result = rpc(client, "tools/call", {"name": "generateDesign", "arguments": arguments}).json()["result"]
    assert result["isError"]

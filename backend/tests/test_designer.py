"""Studio 대신 가짜 도구 호출로 설계·저장·차단 경계를 확인한다."""
import json

import pytest

from app import db
from app.agents import orchestrator, runner
from app.agents.designer import create_draft
from app.contracts import Ir, StructuredRequirements
from app.schemas import IoRow
from test_agents import KEY
from test_contracts import load
from test_mcp import call


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")


def prepare(client, name="self_hold"):
    req = load(name)["requirements"]
    payload = {
        "plc_config": req["plc_config"], "io_list": req["io_list"],
        "conditions": [{"id": c["id"], "text": c["text"], "must_pass": c["must_pass"]} for c in req["conditions"]],
    }
    response = client.post("/projects", json=payload)
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    job = client.post(f"/agent/projects/{pid}/jobs", headers=KEY).json()["job"]["job_id"]
    analysis = {k: v for k, v in req.items() if k not in {"plc_config", "io_list"}}
    response = client.post(f"/agent/jobs/{job}/requirements", headers=KEY, json=analysis)
    assert response.json()["state"] == "DESIGNING", response.text
    return pid, job


def test_rest_generates_stores_and_returns_same_draft(client):
    pid, job = prepare(client)
    response = client.post(f"/agent/jobs/{job}/design", headers=KEY)
    assert response.status_code == 200
    result = response.json()
    assert result["job"]["state"] == "DESIGNING"
    design = result["design"]
    assert Ir.model_validate(design["ir"]) == Ir.model_validate(load("self_hold")["ir"])
    assert [row["device"] for row in design["io_used"]] == ["X1", "X2", "Y0"]
    assert design["explanation"][0]["condition_ids"] == ["C1", "C2"]
    assert design["safety_review"] == design["verification"] == "not_run"
    assert "실제 설비 적용 전 전문가 확인 필요" in design["notice"]
    events = db.list_events(job)
    assert events[design["requirements_event_index"]]["kind"] == "requirements"
    assert client.post(f"/agent/jobs/{job}/design", headers=KEY).json() == result
    assert sum(e["kind"] == "design" for e in db.list_events(job)) == 1
    saved = client.get(f"/agent/jobs/{job}", headers=KEY).json()
    assert saved["job"]["events"][-1]["data"] == design
    assert client.get(f"/projects/{pid}/status").json()["events"][-1]["data"] == design
    assert client.post(f"/agent/jobs/{job}/verification", headers=KEY, json={"passed": True}).status_code == 409
    assert not any(e["state"] in {"VERIFYING", "COMPLETED"} for e in db.list_events(job))


def test_mcp_runs_design_from_saved_requirements(client):
    _, job = prepare(client)
    error, data = call(client, "generateDesign", {"job_id": job})
    assert not error
    assert data["job"]["state"] == "DESIGNING"
    assert data["design"]["ir"]["rungs"][0]["outputs"][0]["target"] == "Y0"


@pytest.mark.parametrize("name", ["on_delay", "estop_interlock"])
def test_unsupported_examples_fail_and_record_reason(client, name):
    _, job = prepare(client, name)
    error, text = call(client, "generateDesign", {"job_id": job})
    assert error
    data = json.loads(text)
    assert data["job"]["state"] == "FAILED"
    assert data["error"]
    assert any(e["kind"] == "design_error" and not e["data"]["retryable"] for e in db.list_events(job))
    assert not any(e["kind"] == "design" for e in db.list_events(job))
    assert client.post(f"/agent/jobs/{job}/design", headers=KEY).status_code == 409


def test_no_saved_requirements_is_failed(client):
    job = db.create_job("no-project", "DESIGNING")["id"]
    result = orchestrator.generate_design(job)
    assert result["job"]["state"] == "FAILED"
    assert "분석 결과가 없어요" in result["error"]


def test_auth_unknown_job_and_wrong_state(client, monkeypatch):
    _, job = prepare(client)
    assert client.post(f"/agent/jobs/{job}/design").status_code == 401
    assert client.post("/agent/jobs/missing/design", headers=KEY).status_code == 404
    db.update_job(job, "ANALYZING")
    assert client.post(f"/agent/jobs/{job}/design", headers=KEY).status_code == 409
    monkeypatch.delenv("AGENT_API_KEY")
    assert client.post(f"/agent/jobs/{job}/design", headers=KEY).status_code == 503


def test_only_used_addresses_are_in_signal_table():
    req = StructuredRequirements.model_validate(load("self_hold")["requirements"])
    req.io_list.append(IoRow(device="X3", name="SPARE", kind="센서"))
    req.assumptions = ["정지 후 시작 버튼을 다시 눌러요."]
    draft = create_draft(req)
    assert len(draft["io_used"]) == 3
    assert draft["assumptions"] == req.assumptions


@pytest.mark.parametrize("change", ["retentive", "alarm", "modes", "series"])
def test_unsupported_configuration(change):
    req = StructuredRequirements.model_validate(load("self_hold")["requirements"])
    setattr(req.plc_config, change, ["수동"] if change == "modes" else "iQ-R" if change == "series" else True)
    with pytest.raises(ValueError):
        create_draft(req)


def test_disallowed_instruction_fails_job(client, monkeypatch):
    _, job = prepare(client)
    monkeypatch.setattr("app.plc.self_hold.load_instructions", lambda: {"series": {"Q": ["LD", "OR", "AND"]}})
    result = client.post(f"/agent/jobs/{job}/design", headers=KEY).json()
    assert result["job"]["state"] == "FAILED"
    assert "OUT" in result["error"]


def test_directline_message_routes_design_without_changing_job_id():
    text = runner._message("project-1", "job-1")
    assert "project_id=project-1 job_id=job-1" in text
    assert "submitRequirements" in text and "generateDesign" in text


def test_fake_studio_analyzes_then_calls_designer(client, monkeypatch):
    req = load("self_hold")["requirements"]
    pid = client.post("/projects", json={
        "plc_config": req["plc_config"], "io_list": req["io_list"],
        "conditions": [{"text": c["text"], "must_pass": True} for c in req["conditions"]],
    }).json()["id"]
    job = client.post(f"/agent/projects/{pid}/jobs", headers=KEY).json()["job"]["job_id"]
    calls = []

    def fake_http(method, url, token=None, body=None):
        if url.endswith("/conversations"):
            return {"conversationId": "fake-studio", "token": "fake-token"}
        if method == "POST":
            assert f"job_id={job}" in body["text"]
            err, _ = call(client, "getJob", {"job_id": job})
            assert not err
            calls.append("getJob")
            analysis = {k: v for k, v in req.items() if k not in {"plc_config", "io_list"}}
            err, data = call(client, "submitRequirements", {"job_id": job, "analysis": analysis})
            assert not err and data["state"] == "DESIGNING"
            calls.append("submitRequirements")
            err, data = call(client, "generateDesign", {"job_id": job})
            assert not err and data["design"]["verification"] == "not_run"
            calls.append("generateDesign")
            return {}
        raise AssertionError("가짜 에이전트가 제출을 마쳤으므로 추가 대기는 필요하지 않아요.")

    monkeypatch.setenv("COPILOT_DIRECTLINE_SECRET", "fake-secret")
    monkeypatch.setattr(runner, "_http", fake_http)
    runner.run_directline(job)
    assert calls == ["getJob", "submitRequirements", "generateDesign"]
    assert db.get_job(job)["state"] == "DESIGNING"
    assert db.get_job(job)["iteration"] == 0
    assert any(e["kind"] == "design" for e in db.list_events(job))

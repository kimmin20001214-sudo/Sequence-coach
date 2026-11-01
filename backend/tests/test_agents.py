import pytest

from app import db
from app.agents import llm, orchestrator
from conftest import valid_project

IO = [
    {"device": "X0", "name": "EMG", "kind": "푸시버튼 NC", "desc": ""},
    {"device": "X1", "name": "START", "kind": "푸시버튼 NO", "desc": ""},
    {"device": "Y0", "name": "MOTOR", "kind": "모터", "desc": ""},
]


def make_project(client, conditions=None):
    p = valid_project()
    p["io_list"] = IO
    p["conditions"] = [{"id": "", "text": t, "must_pass": True} for t in (conditions or ["START 누르면 MOTOR ON"])]
    r = client.post("/projects", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
def reset_llm():
    yield
    llm.set_backend(None)


def fake(conditions, questions=None):
    llm.set_backend(lambda prompt, schema: {"conditions": conditions, "questions": questions or []})


def test_analysis_structures_two_conditions_and_moves_to_designing(client):
    fake([
        {"type": "sequence", "text": "START 누르면 MOTOR ON", "signals": ["START", "MOTOR"]},
        {"type": "safety", "text": "EMG 누르면 모두 OFF", "signals": ["X0"]},
    ])
    pid = make_project(client, ["START 누르면 MOTOR ON", "EMG 누르면 모두 OFF"])
    r = client.post(f"/projects/{pid}/run")
    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "DESIGNING"
    assert [e["state"] for e in body["events"]] == ["INPUT_VALIDATED", "ANALYZING", "DESIGNING"]
    conds = body["events"][-1]["data"]["conditions"]
    assert [c["id"] for c in conds] == ["C1", "C2"]
    assert client.get(f"/projects/{pid}/status").json()["state"] == "DESIGNING"
    assert client.get(f"/projects/{pid}").json()["status"] == "DESIGNING"


def test_emergency_stop_condition_added_automatically(client):
    fake([{"type": "sequence", "text": "START 누르면 MOTOR ON", "signals": ["X1", "Y0"]}])
    pid = make_project(client)
    body = client.post(f"/projects/{pid}/run").json()
    conds = body["events"][-1]["data"]["conditions"]
    assert conds[-1]["type"] == "safety" and conds[-1]["must_pass"] and "X0" in conds[-1]["text"]


def test_unknown_signal_creates_question(client):
    fake([{"type": "sequence", "text": "PUMP 켜기", "signals": ["PUMP"]}])
    pid = make_project(client)
    body = client.post(f"/projects/{pid}/run").json()
    assert body["state"] == "NEEDS_INPUT"
    assert any("PUMP" in q for q in body["questions"])


def test_llm_questions_are_passed_through(client):
    fake([{"type": "sequence", "text": "x", "signals": ["START"]}], questions=["몇 초 동안 켜 둘까요?"])
    body = client.post(f"/projects/{make_project(client)}/run").json()
    assert body["state"] == "NEEDS_INPUT" and "몇 초 동안 켜 둘까요?" in body["questions"]


def test_bad_llm_output_retries_then_fails(client):
    calls = []
    llm.set_backend(lambda p, s: calls.append(1) or {"conditions": [{"type": "nope", "text": "x"}]})
    pid = make_project(client)
    r = client.post(f"/projects/{pid}/run")
    assert r.status_code == 502 and len(calls) == 2
    assert client.get(f"/projects/{pid}/status").json()["state"] == "FAILED"


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert client.post(f"/projects/{make_project(client)}/run").status_code == 503


def test_status_before_run_and_unknown_project(client):
    pid = make_project(client)
    assert client.get(f"/projects/{pid}/status").json()["state"] == "INPUT_VALIDATED"
    assert client.get("/projects/nope/status").status_code == 404
    assert client.post("/projects/nope/run").status_code == 404


def test_escalates_after_max_iter(client):
    job = db.create_job("p1", "VERIFYING", max_iter=2)
    states = []
    for _ in range(3):
        job = orchestrator.report_verification(job["id"], passed=False)
        states.append((job["state"], job["iteration"]))
        if job["state"] == "FIXING":
            db.update_job(job["id"], "VERIFYING")
    assert states == [("FIXING", 1), ("FIXING", 2), ("ESCALATED", 2)]


def test_verification_pass_and_invalid_transition(client):
    job = db.create_job("p1", "VERIFYING")
    assert orchestrator.report_verification(job["id"], passed=True)["state"] == "COMPLETED"
    with pytest.raises(orchestrator.InvalidTransition):
        orchestrator.report_verification(job["id"], passed=True)

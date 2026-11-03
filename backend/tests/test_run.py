"""방향 A: 홈페이지 실행 버튼 → 백엔드 → 에이전트 호출 흐름."""
import pytest

from app import db
from app.agents import runner
from test_agents import KEY, make_project

ENV = ["COPILOT_DIRECTLINE_SECRET", "COPILOT_TOKEN_ENDPOINT", "AGENT_DEMO"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setattr(runner.threading, "Thread", InlineThread)


class InlineThread:
    """테스트에서는 백그라운드 스레드 대신 바로 실행한다."""

    def __init__(self, target, args, daemon=False):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_run_without_agent_is_503(client):
    pid = make_project(client)
    assert client.get("/agent-mode").json() == {"mode": None}
    r = client.post(f"/projects/{pid}/run")
    assert r.status_code == 503 and "연결" in r.json()["detail"]
    assert db.latest_job(pid) is None


def test_run_unknown_project_404(client, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO", "1")
    assert client.post("/projects/nope/run").status_code == 404


def test_demo_run_reaches_designing(client, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO", "1")
    pid = make_project(client)
    assert client.get("/agent-mode").json() == {"mode": "demo"}
    assert client.post(f"/projects/{pid}/run").status_code == 202
    s = client.get(f"/projects/{pid}/status").json()
    assert s["state"] == "DESIGNING"
    assert [e["kind"] for e in s["events"]][:2] == ["created", "started"]
    assert any(e["kind"] == "agent_message" for e in s["events"])
    assert any(e["kind"] == "requirements" for e in s["events"])


def test_agent_failure_marks_failed(client, monkeypatch):
    monkeypatch.setenv("COPILOT_DIRECTLINE_SECRET", "secret-value")

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(runner, "_http", boom)
    pid = make_project(client)
    assert client.post(f"/projects/{pid}/run").status_code == 202
    s = client.get(f"/projects/{pid}/status").json()
    assert s["state"] == "FAILED"
    assert "secret-value" not in str(s)


def test_directline_agent_submits_via_tool_api(client, monkeypatch):
    monkeypatch.setenv("COPILOT_DIRECTLINE_SECRET", "secret-value")
    pid = make_project(client)
    sent = []

    def fake_http(method, url, token=None, body=None):
        if url.endswith("/conversations"):
            return {"conversationId": "c1", "token": "t1"}
        if method == "POST":
            sent.append(body["text"])
            job = db.latest_job(pid)
            analysis = {"conditions": [{"type": "sequence", "text": "START 누르면 MOTOR ON", "signals": ["X1", "Y0"]}]}
            assert client.post(f"/agent/jobs/{job['id']}/requirements", headers=KEY, json=analysis).status_code == 200
            return {}
        return {"watermark": "1", "activities": [{"type": "message", "from": {"id": "bot"}, "text": "분석했어요"}]}

    monkeypatch.setattr(runner, "_http", fake_http)
    assert client.post(f"/projects/{pid}/run").status_code == 202
    job = db.latest_job(pid)
    assert f"job_id={job['id']}" in sent[0] and f"project_id={pid}" in sent[0]
    # 모호한 조건(유지/누르는 동안 불명)은 설계 전에 사용자에게 먼저 묻는다
    assert job["state"] == "NEEDS_INPUT"
    q = next(e for e in db.list_events(job["id"]) if e["kind"] == "questions")
    assert "C1" in q["data"]["questions"][0] and "유지" in q["data"]["questions"][0]


def test_get_job_returns_input_for_agent(client, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO", "1")
    pid = make_project(client)
    client.post(f"/projects/{pid}/run")
    job = db.latest_job(pid)
    r = client.get(f"/agent/jobs/{job['id']}", headers=KEY)
    assert r.status_code == 200 and r.json()["project"]["io_list"][0]["device"] == "X0"
    assert client.get("/agent/jobs/zzz", headers=KEY).status_code == 404
    assert client.get(f"/agent/jobs/{job['id']}").status_code == 401


def test_busy_job_blocks_second_run(client, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO", "1")
    pid = make_project(client)
    db.create_job(pid, "ANALYZING")
    assert client.post(f"/projects/{pid}/run").status_code == 409


def test_vague_condition_asks_then_answer_reanalyzes(client, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO", "1")
    pid = make_project(client, ["START 누르면 잠시 후 MOTOR ON"])
    s = client.post(f"/projects/{pid}/run").json()
    s = client.get(f"/projects/{pid}/status").json()
    assert s["state"] == "NEEDS_INPUT"
    assert len(s["questions"]) == 1 and "잠시" in s["questions"][0]

    answers = [{"question": s["questions"][0], "answer": "3초"}]
    assert client.post(f"/projects/{pid}/run", json={"answers": answers}).status_code == 202
    s2 = client.get(f"/projects/{pid}/status").json()
    assert s2["state"] == "DESIGNING" and s2["job_id"] != s["job_id"]
    req = next(e for e in s2["events"] if e["kind"] == "requirements")["data"]
    assert any("3초" in a for a in req["assumptions"])
    job = db.latest_job(pid)
    assert client.get(f"/agent/jobs/{job['id']}", headers=KEY).json()["project"]["answers"] == answers


def test_number_makes_condition_not_vague(client, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO", "1")
    pid = make_project(client, ["START 누르면 잠시 후(3초) MOTOR ON"])
    client.post(f"/projects/{pid}/run")
    assert client.get(f"/projects/{pid}/status").json()["state"] == "DESIGNING"


def test_agent_unknown_signal_question_then_answer(client, monkeypatch):
    monkeypatch.setenv("COPILOT_DIRECTLINE_SECRET", "s")
    pid = make_project(client)

    def fake_http(method, url, token=None, body=None):
        if url.endswith("/conversations"):
            return {"conversationId": "c1", "token": "t1"}
        if method == "POST":
            job = db.latest_job(pid)
            analysis = {"conditions": [{"type": "sequence", "text": "x", "signals": ["X9"]}]}
            client.post(f"/agent/jobs/{job['id']}/requirements", headers=KEY, json=analysis)
            return {}
        return {"activities": []}

    monkeypatch.setattr(runner, "_http", fake_http)
    client.post(f"/projects/{pid}/run")
    q = client.get(f"/projects/{pid}/status").json()
    assert q["state"] == "NEEDS_INPUT" and "X9" in q["questions"][0]
    client.post(f"/projects/{pid}/run", json={"answers": [{"question": q["questions"][0], "answer": "X1이에요"}]})
    assert client.get(f"/projects/{pid}/status").json()["state"] == "FAILED"
import json

import pytest

from test_agents import KEY, make_project, start


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")


def rpc(client, method, params=None, id_=1, headers=KEY):
    return client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


def call(client, name, args):
    r = rpc(client, "tools/call", {"name": name, "arguments": args}).json()["result"]
    return r["isError"], json.loads(r["content"][0]["text"]) if not r["isError"] else r["content"][0]["text"]


def test_mcp_requires_key(client):
    assert rpc(client, "tools/list", headers={}).status_code == 401


def test_initialize_and_tools_list(client):
    init = rpc(client, "initialize").json()["result"]
    assert init["capabilities"] == {"tools": {}} and init["protocolVersion"]
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "getJob", "submitRequirements", "getStatus", "reportVerification", "startJob",
        "getDesignInput", "validateIr", "submitDesign", "getFixInput", "submitFix",
    }


def test_notification_gets_202(client):
    r = client.post("/mcp", headers=KEY, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202


def test_tools_drive_a_job_to_designing(client):
    pid = make_project(client)
    job_id = start(client, pid)["job"]["job_id"]
    err, data = call(client, "getJob", {"job_id": job_id})
    assert not err and data["project"]["conditions"]
    analysis = {"conditions": [{"type": "sequence", "text": "START 누르면 MOTOR ON 유지", "must_pass": True, "signals": ["START", "MOTOR"]}]}
    err, data = call(client, "submitRequirements", {"job_id": job_id, "analysis": analysis})
    assert not err and data["state"] == "DESIGNING"
    err, data = call(client, "getStatus", {"project_id": pid})
    assert not err and data["state"] == "DESIGNING"


def test_tool_errors_are_reported_not_raised(client):
    err, text = call(client, "getJob", {"job_id": "nope"})
    assert err and "찾을 수 없어요" in text
    err, text = call(client, "submitRequirements", {"job_id": "x", "analysis": {"conditions": "bad"}})
    assert err
    err, _ = call(client, "unknownTool", {})
    assert err


def test_unknown_method(client):
    assert rpc(client, "resources/list").json()["error"]["code"] == -32601

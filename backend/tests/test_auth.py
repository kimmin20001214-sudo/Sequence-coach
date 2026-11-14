import pytest
from fastapi.testclient import TestClient

from app import auth, db, manage
from app.main import app
from conftest import valid_project


@pytest.fixture
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    auth._fails.clear()
    db.create_user("kim", auth.hash_password("password-kim"), "student")
    db.create_user("lee", auth.hash_password("password-lee"), "student")
    return TestClient(app)


def login(c, name="kim", pw="password-kim"):
    return c.post("/auth/login", json={"username": name, "password": pw})


def test_locked_without_login(secured):
    for path in ("/meta", "/projects", "/templates", "/agent-mode", "/auth/me"):
        assert secured.get(path).status_code == 401, path
    assert secured.post("/projects", json=valid_project()).status_code == 401
    assert secured.get("/health").status_code == 200


def test_login_flow_and_logout(secured):
    assert login(secured, pw="wrong-password").status_code == 401
    assert login(secured, "nobody").status_code == 401
    r = login(secured, "KIM")
    assert r.status_code == 200 and r.json()["username"] == "kim"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert secured.get("/auth/me").json()["username"] == "kim"
    assert secured.get("/meta").status_code == 200
    secured.post("/auth/logout")
    assert secured.get("/auth/me").status_code == 401


def test_each_user_sees_only_own_data(secured):
    login(secured)
    pid = secured.post("/projects", json=valid_project()).json()["id"]
    secured.post("/templates", json={"name": "mine", "payload": {"config": {}, "conditions": []}})
    assert secured.get(f"/projects/{pid}").status_code == 200
    secured.post("/auth/logout")
    login(secured, "lee", "password-lee")
    assert secured.get("/projects").json() == []
    assert secured.get(f"/projects/{pid}").status_code == 404
    assert secured.get(f"/projects/{pid}/status").status_code == 404
    assert secured.post(f"/projects/{pid}/run").status_code == 404
    assert all(t["builtin"] for t in secured.get("/templates").json())


def test_lockout_after_repeated_failures(secured):
    for _ in range(auth.MAX_FAILS):
        assert login(secured, pw="bad-password").status_code == 401
    assert login(secured).status_code == 429


def test_disabled_account_and_password_reset_end_sessions(secured):
    login(secured)
    db.set_disabled("kim", True)
    assert secured.get("/auth/me").status_code == 401
    assert login(secured).status_code == 401
    db.set_disabled("kim", False)
    login(secured)
    db.set_password("kim", auth.hash_password("new-password-1"))
    assert secured.get("/auth/me").status_code == 401
    assert login(secured, pw="new-password-1").status_code == 200


def test_agent_api_still_uses_api_key_only(secured, monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "k")
    assert secured.get("/agent/projects/zzz/status").status_code == 401
    r = secured.get("/agent/projects/zzz/status", headers={"X-API-Key": "k"})
    assert r.status_code == 404
    assert secured.get("/agent-spec.json").status_code == 200


def test_production_server_seeds_accounts_and_logs_in(tmp_path, monkeypatch):
    from app.server import server
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "p.sqlite3"))
    monkeypatch.setenv("ACCOUNTS", "boss:long-enough-pw:admin")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    with TestClient(server) as c:
        assert c.get("/api/meta").status_code == 401
        assert c.post("/api/auth/login", json={"username": "boss", "password": "long-enough-pw"}).status_code == 200
        assert c.get("/api/meta").status_code == 200


def test_seed_accounts_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "s.sqlite3"))
    monkeypatch.setenv("ACCOUNTS", "Boss:long-enough-pw:admin, s01:long-enough-pw ,bad:short,s01:other-password")
    auth.seed_accounts()
    assert db.get_user("boss")["role"] == "admin"
    assert db.get_user("s01")["role"] == "student" and db.get_user("bad") is None
    assert auth.verify_password("long-enough-pw", db.get_user("s01")["pw_hash"])


def test_manage_cli_creates_account(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "m.sqlite3"))
    monkeypatch.setattr("getpass.getpass", lambda _="": "long-enough-pw")
    manage.main(["add", "student01"])
    assert db.get_user("student01")["role"] == "student"
    with pytest.raises(SystemExit):
        manage.main(["add", "student01"])
    with pytest.raises(SystemExit):
        manage.main(["add", "A"])

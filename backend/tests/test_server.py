from fastapi.testclient import TestClient


def test_api_prefix_and_static(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    import importlib

    from app import server

    server = importlib.reload(server)
    c = TestClient(server.server)
    assert c.get("/api/health").json() == {"status": "ok"}
    r = c.get("/")
    assert r.status_code == 200 and "ok" in r.text

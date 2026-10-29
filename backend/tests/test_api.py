from app.spec import is_compatible, parse_device
from conftest import valid_project


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_meta(client):
    data = client.get("/meta").json()
    assert set(data["series"]) == {"Q", "iQ-R", "iQ-F"}
    assert "safety_notice" in data and data["options"]["control_targets"]
    assert client.get("/meta/series").json() == ["Q", "iQ-R", "iQ-F"]
    assert is_compatible("Q", "Q06HCPU", "ladder", "GX Works2")
    assert not is_compatible("Q", "Q06HCPU", "ladder", "GX Works3")
    assert "FX5U" in client.get("/meta/cpus", params={"series": "iQ-F"}).json()
    assert "LD" in client.get("/meta/instructions", params={"series": "iQ-R"}).json()
    assert "OUT T" in client.get("/meta/instructions", params={"series": "Q"}).json()
    assert client.get("/meta/cpus", params={"series": "ZZ"}).status_code == 404


def test_compat_and_device_parsing():
    assert is_compatible("iQ-R", "R04CPU", "ladder", "GX Works3")
    assert not is_compatible("iQ-R", "FX5U", "ladder", "GX Works3")
    assert parse_device("X1F", "hex") == ("X", 31)
    assert parse_device("X17", "octal") == ("X", 15)
    assert parse_device("X18", "octal") is None
    assert parse_device("M0", "hex") is None


def test_save_valid_project(client):
    r = client.post("/projects", json=valid_project())
    assert r.status_code == 201
    body = r.json()
    assert body["io_list"][0]["device"] == "X1"
    assert body["conditions"][0]["id"] == "C1"
    assert body["plc_config"]["project_name"].startswith("PRJ_")
    got = client.get(f"/projects/{body['id']}").json()
    assert got["status"] == "RECEIVED" and got["plc_config"]["cpu"] == "R04CPU"
    assert len(client.get("/projects").json()) == 1


def test_incompatible_combo_rejected(client):
    r = client.post("/projects", json=valid_project(cpu="FX5U"))
    assert r.status_code == 422 and "compat" in r.json()["fields"]


def test_points_over_limit(client):
    r = client.post("/projects", json=valid_project(cpu="FX5U", series="iQ-F", x_points=300))
    assert "x_points" in r.json()["fields"]


def test_missing_safety_ack_and_conditions(client):
    p = valid_project(safety_ack=False)
    p["conditions"] = []
    f = client.post("/projects", json=p).json()["fields"]
    assert "safety_ack" in f and "conditions" in f


def test_io_errors(client):
    p = valid_project()
    p["io_list"] = [
        {"device": "X1", "name": "A"}, {"device": "X1", "name": "B"},
        {"device": "X1000", "name": "C"}, {"device": "Z9", "name": "D"}, {"device": "", "name": ""},
    ]
    io = client.post("/validate", json=p).json()["io"]
    assert set(io) == {"1", "2", "3", "4"}


def test_emergency_stop_and_name(client):
    p = valid_project(project_name="bad name!")
    p["plc_config"]["emergency_stop"] = {"used": True, "device": ""}
    f = client.post("/validate", json=p).json()["fields"]
    assert "emergency_stop" in f and "project_name" in f


def test_get_missing_project(client):
    assert client.get("/projects/nope").status_code == 404

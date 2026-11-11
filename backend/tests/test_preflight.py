from app import preflight
from conftest import valid_project


def q(**cfg):
    return valid_project(series="Q", cpu="Q06HCPU", software="GX Works2", **cfg)


def test_supported_setup_passes():
    assert preflight.check(q()) == []


def test_non_q_series_is_blocked():
    assert "Q시리즈" in preflight.check(valid_project())[0]


def test_timer_unit_must_be_100ms():
    assert any("100ms" in m for m in preflight.check(q(timer_unit_ms=10)))


def test_time_in_condition_must_fit_unit():
    p = q()
    p["conditions"] = [{"id": "", "text": "3초 뒤 꺼진다", "must_pass": True},
                       {"id": "", "text": "0.55초 뒤 켜진다", "must_pass": True},
                       {"id": "", "text": "4000초 뒤 켜진다", "must_pass": True}]
    msgs = preflight.check(p)
    assert len(msgs) == 2 and "0.55초" in msgs[0] and "4000초" in msgs[1]


def test_run_endpoint_returns_422_with_reasons(client):
    r = client.post("/projects", json=valid_project())
    assert r.status_code == 201
    r = client.post(f"/projects/{r.json()['id']}/run")
    assert r.status_code == 422 and "Q시리즈" in r.json()["detail"][0]

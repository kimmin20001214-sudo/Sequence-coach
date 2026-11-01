import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.sqlite3"))
    return TestClient(app)


def valid_project(**cfg):
    config = {
        "series": "iQ-R", "cpu": "R04CPU", "language": "ladder", "software": "GX Works3",
        "x_points": 16, "y_points": 16, "control_target": "컨베이어", "safety_ack": True,
        "emergency_stop": {"used": True, "device": "X0"},
    }
    config.update(cfg)
    return {
        "plc_config": config,
        "io_list": [{"device": "x1", "name": "START", "kind": "푸시버튼 NO", "desc": ""}],
        "conditions": [{"id": "", "text": "시작 버튼을 누르면 모터가 켜진다", "must_pass": True}],
    }

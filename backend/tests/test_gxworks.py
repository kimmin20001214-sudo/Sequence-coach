import hashlib
import json
from pathlib import Path

import pytest

from app import db
from app.contracts import Ir
from app.plc.to_gxworks import ExportError, ir_to_il
from app.worker import gx_automation, recorder, sim_runner
from app.worker.common import StepResult, with_retry

FIXTURES = Path(__file__).parent / "fixtures"


def load_ir(name: str) -> Ir:
    return Ir.model_validate(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))["ir"])


def il_lines(name: str) -> list[str]:
    return [l for l in ir_to_il(load_ir(name)).content.splitlines() if not l.startswith(";")]


def test_self_hold_il():
    assert il_lines("self_hold") == ["LD X1", "OR Y0", "AND X2", "OUT Y0", "END"]


def test_export_is_always_unverified():
    r = ir_to_il(load_ir("self_hold"))
    assert r.status == "unverified"
    assert any("확인하지 않았" in n for n in r.notes)


@pytest.mark.parametrize("name", ["on_delay", "estop_interlock"])
def test_fixtures_convert(name):
    lines = il_lines(name)
    assert lines[-1] == "END" and len(lines) > 2


def test_on_delay_uses_timer_unit():
    assert any(l.startswith("OUT ") and " K" in l for l in il_lines("on_delay"))


def test_names_map_to_devices():
    ir = Ir.model_validate({"rungs": [{"id": "R1", "condition": {"type": "contact", "kind": "NO", "signal": "START"},
                                       "outputs": [{"kind": "OUT", "target": "MOTOR"}]}]})
    assert "LD X1" in ir_to_il(ir, {"START": "X1", "MOTOR": "Y0"}).content


def test_nested_blocks_use_anb_orb():
    c = lambda s: {"type": "contact", "kind": "NO", "signal": s}
    ir = Ir.model_validate({"rungs": [{"id": "R1", "outputs": [{"kind": "OUT", "target": "Y0"}], "condition": {
        "type": "AND", "items": [{"type": "OR", "items": [c("X1"), c("X2")]}, {"type": "OR", "items": [c("X3"), c("X4")]}]}}]})
    assert il_lines_of(ir) == ["LD X1", "OR X2", "LD X3", "OR X4", "ANB", "OUT Y0", "END"]


def il_lines_of(ir):
    return [l for l in ir_to_il(ir).content.splitlines() if not l.startswith(";")]


def test_timer_preset_must_match_unit():
    ir = Ir.model_validate({"rungs": [{"id": "R1", "condition": {"type": "contact", "kind": "NO", "signal": "X1"},
                                       "outputs": [{"kind": "TON", "target": "T0", "preset_ms": 150}]}]})
    with pytest.raises(ExportError):
        ir_to_il(ir)


def test_retry_stops_on_success_and_not_run():
    calls = []

    def flaky():
        calls.append(1)
        return StepResult("failed", "x") if len(calls) < 2 else StepResult("completed")

    assert with_retry(flaky).status == "completed" and len(calls) == 2
    n = []
    assert with_retry(lambda: (n.append(1), StepResult("not_run"))[1]).status == "not_run" and len(n) == 1


def test_retry_records_exception_and_gives_up():
    def boom():
        raise RuntimeError("창이 없어요")

    r = with_retry(boom)
    assert r.status == "failed" and len(r.logs) == 3 and "창이 없어요" in r.detail


def test_subtitle_command_has_safety_notice_and_steps():
    cmd = recorder.subtitle_command(Path("a.mp4"), Path("b.mp4"), ["START ON", "STOP ON"], 2.0)
    vf = cmd[cmd.index("-vf") + 1]
    assert "실제 설비 적용 전" in vf and "1. START ON" in vf and "2. STOP ON" in vf


def test_capture_command_uses_gdigrab():
    cmd = recorder.capture_command("GX Simulator", Path("o.mp4"), 10)
    assert "gdigrab" in cmd and "title=GX Simulator" in cmd


def test_missing_tools_report_not_run(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder.shutil, "which", lambda _: None)
    assert recorder.record("x", tmp_path / "o.mp4", 1).status == "not_run"
    monkeypatch.setattr(gx_automation, "available", lambda: False)
    assert gx_automation.import_and_compile(tmp_path / "a.txt", tmp_path).status == "not_run"
    monkeypatch.setattr(sim_runner, "available", lambda: False)
    assert sim_runner.run_scenario([]).status == "not_run"


def test_describe_steps():
    steps = [sim_runner.ScenarioStep("X1", True, ""), sim_runner.ScenarioStep("X2", False, "정지 해제")]
    assert sim_runner.describe(steps) == ["X1 ON", "정지 해제"]


def test_artifacts_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.sqlite3"))
    f = tmp_path / "a.txt"
    f.write_text("LD X1\n", encoding="utf-8")
    db.add_artifact("p1", "gx_il", str(f), hashlib.sha256(f.read_bytes()).hexdigest(), "unverified")
    rows = db.list_artifacts("p1")
    assert len(rows) == 1 and rows[0]["status"] == "unverified" and db.list_artifacts("p2") == []

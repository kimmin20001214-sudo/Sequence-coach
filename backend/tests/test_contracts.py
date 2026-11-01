"""계약 + fixture 점검, 그리고 분석 → 설계 → 검증 통합 테스트 뼈대.

누가 계약(app/contracts.py)을 바꾸면 이 테스트가 바로 실패한다.
각 구현은 아래 STAGES의 자리(stub)를 자기 구현으로 바꾸며 이어 붙인다.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import (
    JOB_TRANSITIONS, Contact, Ir, Output, Parallel, Series, StructuredRequirements,
    VerificationIssue, VerificationResult,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
NAMES = ["self_hold", "on_delay", "estop_interlock"]


def load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def signals_of(node) -> set[str]:
    if isinstance(node, Contact):
        return {node.signal}
    return set().union(*(signals_of(i) for i in node.items))


def known_names(req: StructuredRequirements, ir: Ir) -> set[str]:
    known = {r.device.upper() for r in req.io_list} | {r.name.upper() for r in req.io_list}
    known |= {t.name.upper() for t in req.timers} | {c.name.upper() for c in req.counters}
    return known


@pytest.mark.parametrize("name", NAMES)
def test_fixture_matches_contract(name):
    data = load(name)
    req = StructuredRequirements.model_validate(data["requirements"])
    ir = Ir.model_validate(data["ir"])
    result = VerificationResult.model_validate(data["verification"])
    assert result.passed

    known = known_names(req, ir)
    condition_ids = {c.id for c in req.conditions}
    for rung in ir.rungs:
        assert {s.upper() for s in signals_of(rung.condition)} <= known, rung.id
        assert {o.target.upper() for o in rung.outputs} <= known, rung.id
        assert set(rung.covers) <= condition_ids, rung.id
    assert {c for r in ir.rungs for c in r.covers} == condition_ids


def test_ir_rejects_bad_shapes():
    with pytest.raises(ValidationError):
        Series(items=[])
    with pytest.raises(ValidationError):
        Output(kind="TON", target="T0")
    with pytest.raises(ValidationError):
        Contact(kind="XX", signal="X1")
    assert Parallel(items=[Contact(kind="NO", signal="X1")]).type == "OR"


def test_verification_result_rules():
    issue = VerificationIssue(code="DOUBLE_COIL", message="Y0 출력이 두 번 쓰였어요.", rung_id="R2")
    assert not VerificationResult(passed=False, errors=[issue]).passed
    with pytest.raises(ValidationError):
        VerificationResult(passed=True, errors=[issue])
    with pytest.raises(ValidationError):
        VerificationResult(passed=False)


def test_state_machine_is_closed():
    assert all(t in JOB_TRANSITIONS for targets in JOB_TRANSITIONS.values() for t in targets)
    assert JOB_TRANSITIONS["VERIFYING"] == {"COMPLETED", "FIXING", "ESCALATED"}


# ── 통합 테스트 뼈대 ─────────────────────────────────────────────
# 지금은 fixture를 그대로 돌려주는 stub. 담당자가 자기 구현으로 교체한다.
#   #40 analyze  : ProjectInput → StructuredRequirements
#   #41 design   : StructuredRequirements → Ir
#   #42 verify   : (StructuredRequirements, Ir) → VerificationResult
def analyze(data: dict) -> StructuredRequirements:
    return StructuredRequirements.model_validate(data["requirements"])


def design(req: StructuredRequirements, data: dict) -> Ir:
    return Ir.model_validate(data["ir"])


def verify(req: StructuredRequirements, ir: Ir, data: dict) -> VerificationResult:
    return VerificationResult.model_validate(data["verification"])


@pytest.mark.parametrize("name", NAMES)
def test_pipeline_end_to_end(name):
    data = load(name)
    req = analyze(data)
    ir = design(req, data)
    result = verify(req, ir, data)
    assert result.passed, result.errors

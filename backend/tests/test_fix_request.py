import json
from pathlib import Path

from app.contracts import Ir, StructuredRequirements, VerificationIssue, VerificationResult
from app.plc.fix_request import MAX_CASES, MAX_MESSAGE_LENGTH, build_fix_request


def request_input():
    case = json.loads((Path(__file__).parent / "fixtures/estop_interlock.json").read_text(encoding="utf-8"))
    return StructuredRequirements.model_validate(case["requirements"]), Ir.model_validate(case["ir"])


def test_failure_with_no_rung_and_passed_conditions():
    req, broken = request_input()
    result = VerificationResult(
        passed=False, errors=[VerificationIssue(
            code="UNMET_CONDITION", condition_id="C2", message="지연 회로 누락", rung_id="",
        )], warnings=[VerificationIssue(
            code="CONDITION_PASSED", condition_id="C1", message="통과",
        )],
    )
    request = build_fix_request(req, broken, result)
    missing = next(f for f in request["failed_conditions"] if not f["rung_id"])
    assert missing["id"] == "C2" and missing["text"] == req.conditions[1].text
    assert "이 조건을 만드는 렁이 없어요" in missing["message"]
    assert any(c["id"] == "C1" for c in request["protected_conditions"])
    assert request["ir"] == broken.model_dump()
    assert request["emergency_stop"] == req.plc_config.emergency_stop.model_dump()
    assert request["io_list"] and request["similar_cases"] == []


def test_message_and_cases_are_bounded_and_series_filtered():
    req, broken = request_input()
    result = VerificationResult(passed=False, errors=[VerificationIssue(
        code="UNMET_CONDITION", condition_id="C2", message="실패" * 5000,
    )])
    cases = [{"plc_series": "iQ-R", "verified": True, "solution": "다른 시리즈"}]
    cases += [{"plc_series": "Q", "verified": False, "solution": "미검증"}]
    cases += [{"plc_series": "Q", "verified": True, "solution": "접점" * 5000}] * (MAX_CASES + 5)
    request = build_fix_request(req, broken, result, cases)
    assert len(request["failed_conditions"][0]["message"]) <= MAX_MESSAGE_LENGTH
    assert len(request["similar_cases"]) == MAX_CASES
    assert all(c["plc_series"] == "Q" and len(c["solution"]) <= MAX_MESSAGE_LENGTH
               for c in request["similar_cases"])
    assert request["limits"]["truncated"]


def test_optional_failure_is_not_protected_and_global_errors_are_kept():
    req, broken = request_input()
    result = VerificationResult(
        passed=False,
        errors=[VerificationIssue(code="DOUBLE_COIL", message="중복 출력", rung_id="R2")],
        warnings=[
            VerificationIssue(code="CONDITION_PASSED", message="통과", condition_id="C1"),
            VerificationIssue(code="UNMET_CONDITION", message="실패", condition_id="C1"),
        ],
    )
    request = build_fix_request(req, broken, result)
    assert request["protected_conditions"] == []
    assert request["problems"][0]["code"] == "DOUBLE_COIL"
    assert request["failed_conditions"][0]["id"] == "C1"

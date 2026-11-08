import json
import sqlite3

import pytest

from app.plc.error_knowledge import build_signature, find_similar, save_verified_fix
from app.plc.fix_check import check_fix
from app.plc.verify import verify_with_checks
from test_fix_check import interlock_pair


@pytest.fixture
def knowledge_db(tmp_path, monkeypatch):
    path = tmp_path / "knowledge.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    return path


def save_case(series="Q", solution="역방향 렁에 정방향 NC 접점 추가", **overrides):
    req, broken, fixed = interlock_pair()
    checked = check_fix(req, broken, fixed, verify_with_checks(req, broken))
    args = dict(
        check=checked, project_id="project-1", from_version="v1", to_version="v2",
        plc_series=series, error_signature=build_signature(series, "interlock", "UNMET_CONDITION"),
        symptom="정방향과 역방향 동시 켜짐", root_cause="인터록 접점 누락",
        solution=solution, privacy_reviewed=True,
    )
    args.update(overrides)
    return save_verified_fix(**args)


def test_verified_fix_and_report_persist_and_duplicate_increments_count(knowledge_db):
    saved = save_case()
    assert saved["knowledge"]["verified"] == 1 and saved["knowledge"]["hit_count"] == 1
    again = save_case()
    assert again["knowledge"]["id"] == saved["knowledge"]["id"]
    assert again["knowledge"]["hit_count"] == 2
    with sqlite3.connect(knowledge_db) as con:
        reports = con.execute("SELECT project_id, from_version, to_version, diff_json FROM fix_reports").fetchall()
        assert len(reports) == 2
        assert reports[0][:3] == ("project-1", "v1", "v2")
        assert not json.loads(reports[0][3])["same"]
        assert con.execute("SELECT count(*) FROM error_knowledge").fetchone()[0] == 1


def test_lookup_never_mixes_series_and_exact_match_precedes_keywords(knowledge_db):
    save_case()
    # 다른 시리즈의 기존 자료를 직접 넣어 Q의 판정 결과를 다른 시리즈에 쓰지 않는다.
    with sqlite3.connect(knowledge_db) as con:
        con.execute(
            "INSERT INTO error_knowledge SELECT 'other', 'iQ-R', 'iQ-R|interlock|UNMET_CONDITION', "
            "symptom, root_cause, solution, 1, 1, created_at FROM error_knowledge LIMIT 1"
        )
    exact = find_similar("Q", "Q|interlock|UNMET_CONDITION", ["없는 키워드"])
    assert len(exact) == 1 and exact[0]["plc_series"] == "Q"
    assert find_similar("Q", "Q|timing|UNMET_CONDITION", ["동시"])
    assert find_similar("Q", "Q|timing|UNMET_CONDITION", ["%"]) == []
    assert find_similar("Q", "Q|timing|UNMET_CONDITION", []) == []
    assert find_similar("Q", "Q|timing|UNMET_CONDITION", ["없는 키워드"]) == []
    assert all(c["plc_series"] == "iQ-R" for c in find_similar(
        "iQ-R", "iQ-R|interlock|UNMET_CONDITION", ["동시"],
    ))


def test_unverified_solution_and_claimed_success_are_not_saved(knowledge_db):
    req, broken, _ = interlock_pair()
    failed = check_fix(req, broken, broken, verify_with_checks(req, broken))
    with pytest.raises(ValueError, match="통과"):
        save_case(check=failed)
    failed.ok = True
    with pytest.raises(ValueError, match="통과"):
        save_case(check=failed)
    with sqlite3.connect(knowledge_db) as con:
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0


@pytest.mark.parametrize("overrides", [
    {"privacy_reviewed": False},
    {"solution": "설명" * 5000},
    {"error_signature": "iQ-R|interlock|UNMET_CONDITION"},
    {"plc_series": "iQ-R"},
])
def test_private_oversize_or_mismatched_data_is_rejected(knowledge_db, overrides):
    with pytest.raises(ValueError):
        save_case(**overrides)


def test_unverified_existing_cases_are_not_returned(knowledge_db):
    save_case()
    with sqlite3.connect(knowledge_db) as con:
        con.execute("UPDATE error_knowledge SET verified = 0")
    assert find_similar("Q", "Q|interlock|UNMET_CONDITION", ["동시"]) == []

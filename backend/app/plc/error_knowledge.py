"""검증된 오류 사례와 수정 보고서만 저장한다. API·상태 전이에는 연결하지 않는다.

DATABASE_PATH(기본 data.sqlite3)를 기존 db.py와 공유하지만 연결은 직접 열고 닫는다.
팀장이 통합할 때 _create_tables의 DDL을 db._connect로 옮기고 연결 경로를 일원화할 수 있다.
from_version/to_version은 프로젝트의 외부 버전 식별자다. Ir.version=1은 형식 버전이다.
diff_json에는 변경 비교와 전/후 회로를 보관한다. 자유 입력과 회로 설명의 개인정보·비밀값을
호출자가 확인한 뒤 privacy_reviewed=True로 저장해야 한다. 자동 탐지로 안전을 보장하지 않는다.
"""
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import get_args

from ..contracts import ConditionType
from .fix_check import FixCheck
from .fix_request import MAX_CASES
from .ir_diff import diff_ir

MAX_TEXT_LENGTH = 1000
MAX_REPORT_LENGTH = 200_000
MAX_KEYWORDS = 8


def _text(value: str, label: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label}은 비어 있지 않은 {limit}자 이하 문장이어야 해요.")
    return value


def build_signature(series: str, condition_type: str, failure_code: str) -> str:
    """같은 시리즈·조건 종류·실패 코드를 정확 검색할 키를 만든다."""
    _text(series, "PLC 시리즈", 32)
    _text(failure_code, "실패 코드", 100)
    if condition_type not in get_args(ConditionType) or "|" in series or "|" in failure_code:
        raise ValueError("오류 시그니처의 시리즈·조건 종류·실패 코드가 올바르지 않아요.")
    return f"{series}|{condition_type}|{failure_code}"


def _validate_signature(series: str, signature: str) -> None:
    parts = signature.split("|")
    if len(parts) != 3 or parts[0] != series or build_signature(*parts) != signature:
        raise ValueError("오류 시그니처가 PLC 시리즈와 맞지 않아요.")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(os.environ.get("DATABASE_PATH", "data.sqlite3"))
    con.row_factory = sqlite3.Row
    return con


def _create_tables(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS fix_reports ("
        "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, from_version TEXT NOT NULL, "
        "to_version TEXT NOT NULL, change_summary TEXT NOT NULL, diff_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS error_knowledge ("
        "id TEXT PRIMARY KEY, plc_series TEXT NOT NULL, error_signature TEXT NOT NULL, "
        "symptom TEXT NOT NULL, root_cause TEXT NOT NULL, solution TEXT NOT NULL, "
        "hit_count INTEGER NOT NULL DEFAULT 1, verified INTEGER NOT NULL CHECK (verified IN (0, 1)), "
        "created_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS error_knowledge_solution "
        "ON error_knowledge (plc_series, error_signature, solution)"
    )


def find_similar(series: str, signature: str, symptom_keywords: list[str]) -> list[dict]:
    """같은 시리즈의 검증된 사례를 최대 5개 반환한다. 정확 일치가 없으면 키워드를 찾는다."""
    _validate_signature(series, signature)
    if len(symptom_keywords) > MAX_KEYWORDS:
        raise ValueError(f"증상 키워드는 {MAX_KEYWORDS}개 이하여야 해요.")
    keywords = [_text(word, "증상 키워드", 100) for word in symptom_keywords]
    with closing(_connect()) as con, con:
        _create_tables(con)
        rows = con.execute(
            "SELECT * FROM error_knowledge WHERE plc_series = ? AND error_signature = ? AND verified = 1 "
            "ORDER BY hit_count DESC, created_at DESC, id LIMIT ?",
            (series, signature, MAX_CASES),
        ).fetchall()
        if not rows and keywords:
            patterns = ["%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                        for word in keywords]
            query = " OR ".join("symptom LIKE ? ESCAPE '\\'" for _ in keywords)
            rows = con.execute(
                "SELECT * FROM error_knowledge WHERE plc_series = ? AND verified = 1 AND (" + query + ") "
                "ORDER BY hit_count DESC, created_at DESC, id LIMIT ?",
                (series, *patterns, MAX_CASES),
            ).fetchall()
    return [dict(row) for row in rows]


def _check_report_strings(value: object) -> None:
    if isinstance(value, str) and len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"회로 설명과 비교 문장은 {MAX_TEXT_LENGTH}자 이하여야 해요.")
    if isinstance(value, dict):
        for item in value.values():
            _check_report_strings(item)
    elif isinstance(value, list):
        for item in value:
            _check_report_strings(item)


def save_verified_fix(
    check: FixCheck, project_id: str, from_version: str, to_version: str,
    plc_series: str, error_signature: str, symptom: str, root_cause: str, solution: str,
    *, privacy_reviewed: bool = False,
) -> dict:
    """보고서·해결법을 한 트랜잭션으로 저장한다. 중복 해결법은 hit_count만 증가한다.

    개인정보 검토는 증상·원인·해결 문장, 수정 이유, 전/후 회로 설명 모두를 포함한다.
    잘못된 입력은 ValueError를 내며 DB에 쓰지 않는다. 학생의 실제 사용 확인을 대신하지 않는다.
    """
    if (not check.ok or check.result is None or not check.result.passed or check.result.errors
            or check.regressions or not check.diff or check.diff.get("same") is not False
            or check.old_ir is None or check.new_ir is None):
        raise ValueError("코드의 전체 재검증을 통과한 수정 결과만 저장할 수 있어요.")
    if check.plc_series != plc_series:
        raise ValueError("검증한 PLC 시리즈와 저장할 시리즈가 달라요.")
    if privacy_reviewed is not True:
        raise ValueError("개인정보·비밀값이 없는지 먼저 검토해 주세요.")
    _validate_signature(plc_series, error_signature)
    for value, label, limit in (
        (project_id, "프로젝트 ID", 100), (from_version, "이전 버전", 100),
        (to_version, "새 버전", 100), (symptom, "증상", MAX_TEXT_LENGTH),
        (root_cause, "원인", MAX_TEXT_LENGTH), (solution, "해결법", MAX_TEXT_LENGTH),
        (check.reason, "수정 이유", 2000),
    ):
        _text(value, label, limit)
    if from_version == to_version:
        raise ValueError("이전 버전과 새 버전은 달라야 해요.")
    actual_diff = diff_ir(check.old_ir, check.new_ir)
    if actual_diff["same"] or actual_diff != check.diff:
        raise ValueError("저장할 전/후 회로가 검증된 변경 비교와 맞지 않아요.")
    report_data = {**actual_diff, "old_ir": check.old_ir.model_dump(), "new_ir": check.new_ir.model_dump()}
    _check_report_strings(report_data)
    diff_json = json.dumps(report_data, ensure_ascii=False)
    if len(diff_json) > MAX_REPORT_LENGTH:
        raise ValueError("수정 보고서가 너무 커요.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = {
        "id": uuid.uuid4().hex, "project_id": project_id, "from_version": from_version,
        "to_version": to_version, "change_summary": check.reason, "diff_json": diff_json, "created_at": now,
    }
    with closing(_connect()) as con, con:
        _create_tables(con)
        con.execute(
            "INSERT INTO error_knowledge VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?) "
            "ON CONFLICT (plc_series, error_signature, solution) DO UPDATE "
            "SET hit_count = error_knowledge.hit_count + 1",
            (uuid.uuid4().hex, plc_series, error_signature, symptom, root_cause, solution, now),
        )
        con.execute(
            "INSERT INTO fix_reports VALUES "
            "(:id, :project_id, :from_version, :to_version, :change_summary, :diff_json, :created_at)",
            report,
        )
        knowledge = con.execute(
            "SELECT * FROM error_knowledge WHERE plc_series = ? AND error_signature = ? AND solution = ?",
            (plc_series, error_signature, solution),
        ).fetchone()
    return {"report": report, "knowledge": dict(knowledge)}

"""프로젝트 저장소. 로컬 개발은 SQLite(파일), 배포 시 PostgreSQL로 교체한다."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone


def _db_path() -> str:
    return os.environ.get("DATABASE_PATH", "data.sqlite3")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    con.execute(
        "CREATE TABLE IF NOT EXISTS projects ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, "
        "status TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS templates ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    return con


def list_templates() -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
    return [
        {"id": r["id"], "name": r["name"], "builtin": False, "payload": json.loads(r["payload"])} for r in rows
    ]


def create_template(name: str, payload: dict) -> dict:
    tid = "user-" + uuid.uuid4().hex[:10]
    with _connect() as con:
        con.execute(
            "INSERT INTO templates VALUES (?, ?, ?, ?)",
            (tid, name, json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return {"id": tid, "name": name, "builtin": False, "payload": payload}


def delete_template(tid: str) -> bool:
    with _connect() as con:
        return con.execute("DELETE FROM templates WHERE id = ?", (tid,)).rowcount > 0


def create_project(name: str, payload: dict) -> dict:
    row = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "status": "RECEIVED",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _connect() as con:
        con.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
            (row["id"], name, json.dumps(payload, ensure_ascii=False), row["status"], row["created_at"]),
        )
    return {**row, **payload}


def get_project(project_id: str) -> dict | None:
    with _connect() as con:
        r = con.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "status": r["status"], "created_at": r["created_at"], **json.loads(r["payload"])}


def list_projects() -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT id, name, status, created_at FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

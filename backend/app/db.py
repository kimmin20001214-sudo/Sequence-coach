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
    con.execute(
        "CREATE TABLE IF NOT EXISTS jobs ("
        "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL, "
        "iteration INTEGER NOT NULL, max_iter INTEGER NOT NULL, updated_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS job_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, state TEXT NOT NULL, "
        "kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS artifacts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, type TEXT NOT NULL, "
        "path TEXT NOT NULL, checksum TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_job(project_id: str, state: str, max_iter: int = 5) -> dict:
    job = {"id": uuid.uuid4().hex[:12], "project_id": project_id, "state": state, "iteration": 0,
           "max_iter": max_iter, "updated_at": _now()}
    with _connect() as con:
        con.execute("INSERT INTO jobs VALUES (:id, :project_id, :state, :iteration, :max_iter, :updated_at)", job)
    return job


def get_job(job_id: str) -> dict | None:
    with _connect() as con:
        r = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(r) if r else None


def latest_job(project_id: str) -> dict | None:
    with _connect() as con:
        r = con.execute(
            "SELECT * FROM jobs WHERE project_id = ? ORDER BY updated_at DESC, rowid DESC LIMIT 1", (project_id,)
        ).fetchone()
    return dict(r) if r else None


def update_job(job_id: str, state: str, iteration: int | None = None) -> None:
    with _connect() as con:
        if iteration is None:
            con.execute("UPDATE jobs SET state = ?, updated_at = ? WHERE id = ?", (state, _now(), job_id))
        else:
            con.execute(
                "UPDATE jobs SET state = ?, iteration = ?, updated_at = ? WHERE id = ?",
                (state, iteration, _now(), job_id),
            )


def add_event(job_id: str, state: str, kind: str, data: dict) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO job_events (job_id, state, kind, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, state, kind, json.dumps(data, ensure_ascii=False), _now()),
        )


def list_events(job_id: str) -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM job_events WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
    return [
        {"state": r["state"], "kind": r["kind"], "data": json.loads(r["data"]), "created_at": r["created_at"]}
        for r in rows
    ]


def add_artifact(project_id: str, type: str, path: str, checksum: str, status: str) -> dict:
    """산출물(gx_il, video 등) 경로와 체크섬을 기록한다. status는 호환성·실행 상태(예: unverified)."""
    row = {"project_id": project_id, "type": type, "path": path, "checksum": checksum, "status": status,
           "created_at": _now()}
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO artifacts (project_id, type, path, checksum, status, created_at) "
            "VALUES (:project_id, :type, :path, :checksum, :status, :created_at)", row)
    return {"id": cur.lastrowid, **row}


def list_artifacts(project_id: str) -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM artifacts WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()
    return [dict(r) for r in rows]


def update_project_status(project_id: str, status: str) -> None:
    with _connect() as con:
        con.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))


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

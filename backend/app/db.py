"""프로젝트 저장소. 로컬 개발은 SQLite(파일), 배포 시 PostgreSQL로 교체한다."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone


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
        "CREATE TABLE IF NOT EXISTS users ("
        "username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, role TEXT NOT NULL, "
        "disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at TEXT NOT NULL)"
    )
    for table in ("projects", "templates"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if "owner" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
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


def update_project_status(project_id: str, status: str) -> None:
    with _connect() as con:
        con.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))


def list_templates(owner: str = "") -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM templates WHERE owner = ? ORDER BY created_at DESC", (owner,)).fetchall()
    return [
        {"id": r["id"], "name": r["name"], "builtin": False, "payload": json.loads(r["payload"])} for r in rows
    ]


def create_template(name: str, payload: dict, owner: str = "") -> dict:
    tid = "user-" + uuid.uuid4().hex[:10]
    with _connect() as con:
        con.execute(
            "INSERT INTO templates (id, name, payload, created_at, owner) VALUES (?, ?, ?, ?, ?)",
            (tid, name, json.dumps(payload, ensure_ascii=False), _now(), owner),
        )
    return {"id": tid, "name": name, "builtin": False, "payload": payload}


def delete_template(tid: str, owner: str = "") -> bool:
    with _connect() as con:
        return con.execute("DELETE FROM templates WHERE id = ? AND owner = ?", (tid, owner)).rowcount > 0


def project_owner(project_id: str) -> str | None:
    with _connect() as con:
        r = con.execute("SELECT owner FROM projects WHERE id = ?", (project_id,)).fetchone()
    return r["owner"] if r else None


def create_user(username: str, pw_hash: str, role: str) -> bool:
    with _connect() as con:
        try:
            con.execute("INSERT INTO users (username, pw_hash, role, created_at) VALUES (?, ?, ?, ?)",
                        (username, pw_hash, role, _now()))
        except sqlite3.IntegrityError:
            return False
    return True


def get_user(username: str) -> dict | None:
    with _connect() as con:
        r = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(r) if r else None


def list_users() -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT username, role, disabled, created_at FROM users ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def set_password(username: str, pw_hash: str) -> bool:
    with _connect() as con:
        ok = con.execute("UPDATE users SET pw_hash = ? WHERE username = ?", (pw_hash, username)).rowcount > 0
        con.execute("DELETE FROM sessions WHERE username = ?", (username,))
    return ok


def set_disabled(username: str, disabled: bool) -> bool:
    with _connect() as con:
        ok = con.execute("UPDATE users SET disabled = ? WHERE username = ?", (int(disabled), username)).rowcount > 0
        if disabled:
            con.execute("DELETE FROM sessions WHERE username = ?", (username,))
    return ok


def create_session(token_hash: str, username: str, hours: int) -> None:
    expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")
    with _connect() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
        con.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, username, expires))


def user_for_session(token_hash: str) -> dict | None:
    with _connect() as con:
        r = con.execute(
            "SELECT u.username, u.role FROM sessions s JOIN users u ON u.username = s.username "
            "WHERE s.token_hash = ? AND s.expires_at > ? AND u.disabled = 0", (token_hash, _now()),
        ).fetchone()
    return dict(r) if r else None


def delete_session(token_hash: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def create_project(name: str, payload: dict, owner: str = "") -> dict:
    row = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "status": "RECEIVED",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _connect() as con:
        con.execute(
            "INSERT INTO projects (id, name, payload, status, created_at, owner) VALUES (?, ?, ?, ?, ?, ?)",
            (row["id"], name, json.dumps(payload, ensure_ascii=False), row["status"], row["created_at"], owner),
        )
    return {**row, **payload}


def get_project(project_id: str) -> dict | None:
    with _connect() as con:
        r = con.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "status": r["status"], "created_at": r["created_at"], **json.loads(r["payload"])}


def list_projects(owner: str = "") -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, name, status, created_at FROM projects WHERE owner = ? ORDER BY created_at DESC", (owner,)
        ).fetchall()
    return [dict(r) for r in rows]

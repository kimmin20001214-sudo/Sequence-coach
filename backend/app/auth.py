"""로그인. 팀장이 계정을 만들고(app.manage), 학생은 아이디·비밀번호로 로그인한다.

로그인하면 서버가 무작위 세션 값을 쿠키(HttpOnly)로 준다. DB에는 세션 값의 해시만 저장한다.
AUTH_DISABLED=1 이면 로그인을 건너뛴다(로컬 개발·테스트 전용).
"""
import hashlib
import hmac
import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db

COOKIE = "plc_session"
SESSION_HOURS = 12
MIN_PASSWORD = 8
MAX_FAILS = 5
LOCK_SECONDS = 60

_fails: dict[str, tuple[int, float]] = {}


def disabled() -> bool:
    return os.environ.get("AUTH_DISABLED") == "1"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(got, bytes.fromhex(digest))
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request) -> dict:
    if disabled():
        return {"username": "", "role": "admin"}
    token = request.cookies.get(COOKIE)
    user = db.user_for_session(_token_hash(token)) if token else None
    if not user:
        raise HTTPException(401, "로그인이 필요해요.")
    return user


def own_project(project_id: str, user: dict) -> None:
    """남의 프로젝트는 '없는 것'처럼 404로 답한다."""
    owner = db.project_owner(project_id)
    if owner is None or owner != user["username"]:
        raise HTTPException(404, "프로젝트를 찾을 수 없어요.")


def seed_accounts() -> None:
    """ACCOUNTS="leader:비밀번호:admin,s01:비밀번호" 형식의 환경변수로 없는 계정만 만든다.
    셸을 못 쓰는 배포 환경(무료 호스팅)에서 계정을 만들거나, 재시작으로 DB가 비었을 때 복구하는 용도다."""
    for item in filter(None, (s.strip() for s in os.environ.get("ACCOUNTS", "").split(","))):
        name, _, rest = item.partition(":")
        password, _, role = rest.partition(":")
        name = name.strip().lower()
        if not name or len(password) < MIN_PASSWORD:
            continue
        existing = db.get_user(name)
        if not existing:
            db.create_user(name, hash_password(password), "admin" if role == "admin" else "student")
        elif not verify_password(password, existing["pw_hash"]):
            db.set_password(name, hash_password(password))


router = APIRouter(prefix="/auth", tags=["auth"])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    name = body.username.strip().lower()
    fails, until = _fails.get(name, (0, 0.0))
    if fails >= MAX_FAILS and time.time() < until:
        raise HTTPException(429, "로그인에 여러 번 실패했어요. 1분 뒤에 다시 시도해 주세요.")
    user = db.get_user(name)
    ok = verify_password(body.password, user["pw_hash"] if user else hash_password("x")) and bool(user) and not user["disabled"]
    if not ok:
        _fails[name] = (fails + 1, time.time() + LOCK_SECONDS)
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않아요.")
    _fails.pop(name, None)
    token = secrets.token_urlsafe(32)
    db.create_session(_token_hash(token), name, SESSION_HOURS)
    secure = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax", secure=secure)
    return {"username": name, "role": user["role"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        db.delete_session(_token_hash(token))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user

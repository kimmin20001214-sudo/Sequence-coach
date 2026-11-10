"""백엔드 → Copilot Studio 에이전트 호출(방향 A).

홈페이지 실행 버튼이 작업(job)을 만들면, 이 모듈이 에이전트에게 "이 job을 처리해 달라"고 알린다.
에이전트는 /agent/* 도구(방향 B)로 입력을 읽고 결과를 제출한다. 이 모듈은 결과를 기다리며 진행을 기록한다.

설정(환경변수, 저장소에 올리지 않는다)
- COPILOT_DIRECTLINE_SECRET   : Copilot Studio 웹 채널의 Direct Line 시크릿
- COPILOT_TOKEN_ENDPOINT      : 또는 Copilot Studio의 토큰 엔드포인트 URL (시크릿 대신)
- COPILOT_DIRECTLINE_URL      : 기본 https://directline.botframework.com/v3/directline
- COPILOT_TIMEOUT_SECONDS     : 에이전트 응답 대기 시간, 기본 180
- AGENT_DEMO=1                : 에이전트 없이 화면 흐름만 보는 시연 모드(AI 분석 아님)
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from .. import db
from . import orchestrator
from .schemas import LlmAnalysis

DEFAULT_URL = "https://directline.botframework.com/v3/directline"
POLL_SECONDS = 2.0


class AgentNotConfigured(RuntimeError):
    pass


def mode() -> str | None:
    if os.environ.get("COPILOT_DIRECTLINE_SECRET") or os.environ.get("COPILOT_TOKEN_ENDPOINT"):
        return "directline"
    if os.environ.get("AGENT_DEMO") == "1":
        return "demo"
    return None


def _http(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def _initial_token() -> str:
    secret = os.environ.get("COPILOT_DIRECTLINE_SECRET")
    if secret:
        return secret
    return _http("GET", os.environ["COPILOT_TOKEN_ENDPOINT"])["token"]


def _state(job_id: str) -> str:
    return db.get_job(job_id)["state"]


def _message(project_id: str, job_id: str) -> str:
    return (
        f"[작업 시작] project_id={project_id} job_id={job_id}\n"
        "getJob 도구로 이 작업의 입력을 읽어 분석하고, 결과를 submitRequirements 도구로 제출해 주세요."
    )


def _design_message(job_id: str) -> str:
    return (
        f"[설계 시작] job_id={job_id}\n"
        "설계 에이전트에게 맡겨 주세요. getDesignInput으로 분석 결과를 읽어 회로(IR)를 만들고, "
        "validateIr로 고친 뒤 submitDesign으로 제출해야 해요."
    )


def _fix_message(job_id: str) -> str:
    return (
        f"[수정 시작] job_id={job_id}\n"
        "수정 에이전트에게 맡겨 주세요. getFixInput으로 수정 요청을 읽어 회로(IR)를 고치고 "
        "submitFix로 제출해야 해요. 성공 여부는 서버가 다시 검증해서 정해요."
    )


def _designed(job_id: str) -> bool:
    return any(e["kind"] == "design" for e in db.list_events(job_id))


def _wait_verified(job_id: str, seconds: float = 10.0) -> None:
    # 설계 제출 직후 검증이 끝나 FIXING/COMPLETED로 바뀔 때까지 잠깐 기다린다
    deadline = time.monotonic() + seconds
    while _state(job_id) == "VERIFYING" and time.monotonic() < deadline:
        time.sleep(0.2)


def _finished(job_id: str, design: bool, fix: bool, start_iter: int) -> bool:
    if fix:
        return _state(job_id) != "FIXING" or db.get_job(job_id)["iteration"] != start_iter
    if design:
        return _state(job_id) != "DESIGNING" or _designed(job_id)
    return _state(job_id) != "ANALYZING"


def run_directline(job_id: str, design: bool = False, fix: bool = False) -> None:
    base = os.environ.get("COPILOT_DIRECTLINE_URL", DEFAULT_URL).rstrip("/")
    timeout = float(os.environ.get("COPILOT_TIMEOUT_SECONDS", "180"))
    job = db.get_job(job_id)
    start_iter = job["iteration"]
    conv = _http("POST", f"{base}/conversations", _initial_token())
    token, cid = conv.get("token") or _initial_token(), conv["conversationId"]
    _http("POST", f"{base}/conversations/{cid}/activities", token, {
        "type": "message", "from": {"id": "plc-backend"},
        "text": _fix_message(job_id) if fix else _design_message(job_id) if design else _message(job["project_id"], job_id),
    })
    db.add_event(job_id, _state(job_id), "agent_called", {"channel": "directline", "phase": "fix" if fix else "design" if design else "analysis"})

    watermark, deadline = "", time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _finished(job_id, design, fix, start_iter):
            return
        url = f"{base}/conversations/{cid}/activities" + (f"?watermark={watermark}" if watermark else "")
        page = _http("GET", url, token)
        watermark = page.get("watermark", watermark)
        for act in page.get("activities", []):
            if act.get("type") == "message" and act.get("from", {}).get("id") != "plc-backend" and act.get("text"):
                db.add_event(job_id, _state(job_id), "agent_message", {"text": act["text"][:1000]})
        time.sleep(POLL_SECONDS)
    orchestrator.fail_job(job_id, "에이전트가 제한 시간 안에 결과를 보내지 않았어요.")


def run_demo(job_id: str) -> None:
    """시연 모드: 입력 조건을 그대로 조건 목록으로 만들어 제출한다. 실제 AI 분석이 아니다."""
    _, project = orchestrator.get_job_input(job_id)
    db.add_event(job_id, _state(job_id), "agent_message", {"text": "시연 모드: 실제 AI 분석이 아니라 입력 조건을 그대로 옮겼어요."})
    analysis = LlmAnalysis(
        conditions=[{"type": "sequence", "text": c["text"], "must_pass": c["must_pass"]} for c in project["conditions"]],
        assumptions=["시연 모드라 조건을 해석하지 않았어요."],
    )
    orchestrator.submit_requirements(job_id, analysis)


def _run(job_id: str, chosen: str) -> None:
    try:
        (run_directline if chosen == "directline" else run_demo)(job_id)
        if chosen == "directline" and _state(job_id) == "DESIGNING":
            run_directline(job_id, design=True)
        for _ in range(db.get_job(job_id)["max_iter"] + 1):
            _wait_verified(job_id)
            if chosen != "directline" or _state(job_id) != "FIXING":
                break
            run_directline(job_id, fix=True)
    except Exception as e:  # 어떤 실패든 작업이 ANALYZING에 멈추지 않게 기록한다
        reason = f"에이전트 호출에 실패했어요. ({type(e).__name__})"
        if isinstance(e, urllib.error.HTTPError):
            reason = f"에이전트 호출에 실패했어요. (HTTP {e.code})"
        orchestrator.fail_job(job_id, reason)


def launch(job_id: str) -> None:
    chosen = mode()
    if not chosen:
        raise AgentNotConfigured("에이전트가 연결되지 않았어요.")
    threading.Thread(target=_run, args=(job_id, chosen), daemon=True).start()

"""Copilot Studio의 MCP 도구 메뉴에서 쓰는 MCP 서버(Streamable HTTP, JSON 응답).

REST 도구와 같은 기능(agent_api)을 MCP 도구로 노출한다. X-API-Key 헤더 인증은 /agent/*와 같다.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError

from . import agent_api
from .agents.schemas import LlmAnalysis

router = APIRouter(tags=["mcp"], dependencies=[Depends(agent_api.require_key)])

PROTOCOL = "2025-03-26"


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_ID = {"type": "string", "description": "프로젝트 ID"}
_JOB = {"type": "string", "description": "작업(job) ID"}
_IR = {"type": "object", "description": "회로 IR JSON: {version:1, rungs:[{id, comment, condition, outputs, covers}]}"}

TOOLS = [
    {"name": "getDesignInput",
     "description": "설계할 분석 결과(requirements: plc_config, io_list, conditions)를 읽어요. DESIGNING 상태에서만 가능해요.",
     "inputSchema": _obj({"job_id": _JOB}, ["job_id"])},
    {"name": "validateIr",
     "description": "회로(IR)를 저장하지 않고 검사해요. errors가 있으면 고쳐서 다시 검사하세요.",
     "inputSchema": _obj({"job_id": _JOB, "ir": _IR}, ["job_id", "ir"])},
    {"name": "submitDesign",
     "description": "회로(IR)를 제출해요. 검사를 통과하면 저장되고, 거부되면 errors를 돌려줘요. 5번 거부되면 작업이 FAILED가 돼요.",
     "inputSchema": _obj({"job_id": _JOB, "ir": _IR}, ["job_id", "ir"])},
    {"name": "getJob", "description": "백엔드가 시작한 작업(job_id)의 상태와 분석할 입력(plc_config, io_list, conditions, answers)을 돌려줘요.",
     "inputSchema": _obj({"job_id": _JOB}, ["job_id"])},
    {"name": "submitRequirements",
     "description": "분석 결과를 제출해요. I/O 목록에 없는 신호가 있으면 질문이 생기고(NEEDS_INPUT), 없으면 DESIGNING으로 넘어가요.",
     "inputSchema": _obj({"job_id": _JOB, "analysis": LlmAnalysis.model_json_schema()}, ["job_id", "analysis"])},
    {"name": "getStatus", "description": "프로젝트의 가장 최근 작업 상태, 단계별 기록, 사용자에게 물어볼 질문 목록을 돌려줘요.",
     "inputSchema": _obj({"project_id": _ID}, ["project_id"])},
    {"name": "reportVerification", "description": "검증 에이전트가 통과 여부를 보고해요. 실패가 최대 횟수를 넘으면 ESCALATED가 돼요.",
     "inputSchema": _obj({"job_id": _JOB, "passed": {"type": "boolean"}}, ["job_id", "passed"])},
    {"name": "startJob", "description": "에이전트가 직접 새 작업을 시작해요(홈페이지 실행 버튼으로 시작한 작업은 getJob을 쓰세요).",
     "inputSchema": _obj({"project_id": _ID}, ["project_id"])},
]


def _call(name: str, a: dict):
    if name == "getDesignInput":
        return agent_api.get_design_input(a["job_id"])
    if name in ("validateIr", "submitDesign"):
        body = agent_api.IrBody(ir=a["ir"])
        fn = agent_api.validate_ir_tool if name == "validateIr" else agent_api.submit_design
        return fn(a["job_id"], body)
    if name == "getJob":
        return agent_api.get_job(a["job_id"])
    if name == "submitRequirements":
        return agent_api.submit_requirements(a["job_id"], LlmAnalysis(**a["analysis"]))
    if name == "getStatus":
        return agent_api.get_status(a["project_id"])
    if name == "reportVerification":
        return agent_api.report_verification(a["job_id"], agent_api.Verification(passed=a["passed"]))
    if name == "startJob":
        return agent_api.start_job(a["project_id"])
    raise KeyError(name)


def _result(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, code: int, message: str):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _tool_result(id_, text: str, is_error: bool = False):
    return _result(id_, {"content": [{"type": "text", "text": text}], "isError": is_error})


def handle(msg: dict) -> dict | None:
    id_, method = msg.get("id"), msg.get("method")
    if id_ is None:
        return None
    if method == "initialize":
        return _result(id_, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                             "serverInfo": {"name": "melsec-plc-agent-tools", "version": "1.0.0"}})
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": TOOLS})
    if method == "tools/call":
        p = msg.get("params") or {}
        try:
            data = _call(p.get("name", ""), p.get("arguments") or {})
        except KeyError as e:
            return _tool_result(id_, f"알 수 없는 도구이거나 필수 값이 없어요: {e}", True)
        except HTTPException as e:
            return _tool_result(id_, str(e.detail), True)
        except (ValidationError, TypeError) as e:
            return _tool_result(id_, f"입력 형식이 올바르지 않아요: {e}", True)
        if p.get("name") == "submitDesign":
            return _tool_result(id_, json.dumps(data, ensure_ascii=False), not data["ok"])
        return _tool_result(id_, json.dumps(data, ensure_ascii=False))
    return _error(id_, -32601, f"지원하지 않는 메서드: {method}")


@router.post("/mcp", include_in_schema=False)
async def mcp(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return Response(json.dumps(_error(None, -32700, "JSON을 읽을 수 없어요.")), media_type="application/json", status_code=400)
    msgs = body if isinstance(body, list) else [body]
    out = [r for r in (handle(m) for m in msgs if isinstance(m, dict)) if r]
    if not out:
        return Response(status_code=202)
    return Response(json.dumps(out if isinstance(body, list) else out[0], ensure_ascii=False), media_type="application/json")


@router.get("/mcp", include_in_schema=False)
def mcp_get():
    raise HTTPException(405, "POST로 접속하세요.")

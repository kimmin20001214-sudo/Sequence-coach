from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import auth, db
from . import agent_api, mcp_api, run_api
from .schemas import ProjectInput, TemplateInput
from .spec import get_series, load_builtin_templates, load_instructions, load_spec
from .validation import has_errors, validate_project

app = FastAPI(title="MELSEC PLC 회로 설계 지원 API")
api = APIRouter(dependencies=[Depends(auth.current_user)])
app.router.on_startup.append(auth.seed_accounts)
app.include_router(auth.router)
app.include_router(agent_api.router)
app.include_router(run_api.router)
app.include_router(mcp_api.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@api.get("/meta")
def meta():
    """화면이 선택지를 그리는 데 필요한 전체 기준 데이터."""
    return load_spec()


@api.get("/meta/series")
def meta_series():
    return list(load_spec()["series"])


@api.get("/meta/cpus")
def meta_cpus(series: str):
    s = get_series(series)
    if not s:
        raise HTTPException(404, f"알 수 없는 시리즈: {series}")
    return s["cpus"]


@api.get("/meta/instructions")
def meta_instructions(series: str):
    ins = load_instructions()
    if series not in ins["series"]:
        raise HTTPException(404, f"알 수 없는 시리즈: {series}")
    return {name: ins["details"][name] for name in ins["series"][series]}


@api.post("/validate")
def validate(project: ProjectInput):
    result = validate_project(project)
    return {"ok": not has_errors(result), **result}


@api.post("/projects", status_code=201)
def create_project(project: ProjectInput, user: dict = Depends(auth.current_user)):
    result = validate_project(project)
    if has_errors(result):
        return JSONResponse(status_code=422, content={"ok": False, **result})
    payload = project.model_dump()
    cfg = payload["plc_config"]
    cfg["project_name"] = cfg["project_name"] or "PRJ_" + db.uuid.uuid4().hex[:6].upper()
    payload["io_list"] = [
        {**r, "device": r["device"].strip().upper(), "name": r["name"].strip()} for r in payload["io_list"]
    ]
    payload["conditions"] = [
        {**c, "id": f"C{i + 1}", "text": c["text"].strip()} for i, c in enumerate(payload["conditions"]) if c["text"].strip()
    ]
    return db.create_project(cfg["project_name"], payload, user["username"])


@api.get("/templates")
def templates(user: dict = Depends(auth.current_user)):
    return load_builtin_templates() + db.list_templates(user["username"])


@api.post("/templates", status_code=201)
def create_template(t: TemplateInput, user: dict = Depends(auth.current_user)):
    return db.create_template(t.name, t.payload, user["username"])


@api.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str, user: dict = Depends(auth.current_user)):
    if not db.delete_template(template_id, user["username"]):
        raise HTTPException(404, "삭제할 수 있는 템플릿이 없어요. (기본 템플릿은 삭제할 수 없어요.)")


@api.get("/projects/{project_id}/status")
def status(project_id: str, user: dict = Depends(auth.current_user)):
    auth.own_project(project_id, user)
    return agent_api.project_status(project_id)


@app.get("/agent-spec.json", include_in_schema=False)
def agent_spec(request: Request):
    """Copilot Studio에서 도구(REST API)로 가져올 OpenAPI 문서. 접속한 공개 주소를 servers에 넣어요."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return agent_api.build_openapi(f"{proto}://{host}" if host else None)


@api.get("/projects")
def projects(user: dict = Depends(auth.current_user)):
    return db.list_projects(user["username"])


@api.get("/projects/{project_id}")
def project(project_id: str, user: dict = Depends(auth.current_user)):
    auth.own_project(project_id, user)
    found = db.get_project(project_id)
    if not found:
        raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
    return found


app.include_router(api)

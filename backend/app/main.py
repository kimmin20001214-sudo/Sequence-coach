from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import db
from .schemas import ProjectInput, TemplateInput
from .spec import get_series, load_builtin_templates, load_instructions, load_spec
from .validation import has_errors, validate_project

app = FastAPI(title="MELSEC PLC 회로 설계 지원 API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/meta")
def meta():
    """화면이 선택지를 그리는 데 필요한 전체 기준 데이터."""
    return load_spec()


@app.get("/meta/series")
def meta_series():
    return list(load_spec()["series"])


@app.get("/meta/cpus")
def meta_cpus(series: str):
    s = get_series(series)
    if not s:
        raise HTTPException(404, f"알 수 없는 시리즈: {series}")
    return s["cpus"]


@app.get("/meta/instructions")
def meta_instructions(series: str):
    ins = load_instructions()
    if series not in ins["series"]:
        raise HTTPException(404, f"알 수 없는 시리즈: {series}")
    return {name: ins["details"][name] for name in ins["series"][series]}


@app.post("/validate")
def validate(project: ProjectInput):
    result = validate_project(project)
    return {"ok": not has_errors(result), **result}


@app.post("/projects", status_code=201)
def create_project(project: ProjectInput):
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
    return db.create_project(cfg["project_name"], payload)


@app.get("/templates")
def templates():
    return load_builtin_templates() + db.list_templates()


@app.post("/templates", status_code=201)
def create_template(t: TemplateInput):
    return db.create_template(t.name, t.payload)


@app.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str):
    if not db.delete_template(template_id):
        raise HTTPException(404, "삭제할 수 있는 템플릿이 없어요. (기본 템플릿은 삭제할 수 없어요.)")


@app.get("/projects")
def projects():
    return db.list_projects()


@app.get("/projects/{project_id}")
def project(project_id: str):
    found = db.get_project(project_id)
    if not found:
        raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
    return found

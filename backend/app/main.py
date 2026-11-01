from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import db
from .agents import orchestrator
from .agents.llm import LlmUnavailable
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


@app.post("/projects/{project_id}/run", status_code=202)
def run_project(project_id: str):
    """분석 에이전트를 실행한다. 질문이 있으면 NEEDS_INPUT, 없으면 DESIGNING 상태가 된다."""
    try:
        job = orchestrator.start_analysis(project_id)
    except KeyError:
        raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
    except LlmUnavailable as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(502, str(e))
    return _status(job)


@app.get("/projects/{project_id}/status")
def project_status(project_id: str):
    job = db.latest_job(project_id)
    if not job:
        if not db.get_project(project_id):
            raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
        return {"project_id": project_id, "state": "INPUT_VALIDATED", "job_id": None, "iteration": 0, "max_iter": 5,
                "events": [], "questions": []}
    return _status(job)


def _status(job: dict) -> dict:
    events = db.list_events(job["id"])
    questions = next((e["data"].get("questions", []) for e in reversed(events) if e["kind"] == "questions"), [])
    return {"project_id": job["project_id"], "job_id": job["id"], "state": job["state"],
            "iteration": job["iteration"], "max_iter": job["max_iter"], "updated_at": job["updated_at"],
            "events": events, "questions": questions}


@app.get("/projects")
def projects():
    return db.list_projects()


@app.get("/projects/{project_id}")
def project(project_id: str):
    found = db.get_project(project_id)
    if not found:
        raise HTTPException(404, "프로젝트를 찾을 수 없어요.")
    return found

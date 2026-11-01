from app.agents import analyzer
from app.agents.schemas import LlmAnalysis
from app.schemas import ProjectInput
from conftest import valid_project
from test_agents import IO


def project(text="START 누르면 MOTOR ON"):
    p = valid_project()
    p["io_list"] = IO
    p["conditions"] = [{"id": "C1", "text": text, "must_pass": True}]
    return ProjectInput(**p)


def analysis(questions):
    return LlmAnalysis(conditions=[{"type": "sequence", "text": "x", "must_pass": True, "signals": ["START"]}], questions=questions)


def test_questions_are_capped_and_rest_become_assumptions():
    qs = [f"질문{i}" for i in range(6)]
    req = analyzer.finalize(project(), analysis(qs))
    assert req.questions == qs[:3]
    assert sum("질문을 줄이려고 생략" in a for a in req.assumptions) == 3


def test_blocking_questions_come_before_agent_questions():
    req = analyzer.finalize(project("START 누르면 잠시 후 MOTOR ON"), analysis(["a", "b", "c", "d"]))
    assert "잠시" in req.questions[0]
    assert req.questions[1:] == ["a", "b"]

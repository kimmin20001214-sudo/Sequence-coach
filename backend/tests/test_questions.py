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


def test_no_agent_questions_after_user_answered():
    answers = [{"question": "질문0", "answer": "예"}]
    req = analyzer.finalize(project(), analysis(["질문0", "말만 바꾼 질문"]), answers)
    assert req.questions == []
    assert any("말만 바꾼 질문" in a for a in req.assumptions)


def test_vague_question_not_duplicated_by_agent():
    req = analyzer.finalize(project("START 누르면 잠시 후 MOTOR ON"), analysis(["C1에서 '잠시 후'는 몇 초인가요?"]))
    assert len(req.questions) == 1


def test_vague_question_not_repeated_when_answered_in_agent_wording():
    answers = [{"question": "C1의 '잠시 후'는 몇 초 후입니까?", "answer": "2초"}]
    req = analyzer.finalize(project("START 누르면 잠시 후 MOTOR ON"), analysis([]), answers)
    assert req.questions == []


def test_vague_question_not_repeated_when_answered_by_condition_id():
    answers = [{"question": "C1에서 STOP_PB 지연은 몇 초입니까?", "answer": "3초"}]
    req = analyzer.finalize(project("START 누르면 잠시 후 MOTOR ON"), analysis([]), answers)
    assert req.questions == []


def test_blocking_questions_come_before_agent_questions():
    req = analyzer.finalize(project("START 누르면 잠시 후 MOTOR ON"), analysis(["a", "b", "c", "d"]))
    assert "잠시" in req.questions[0]
    assert req.questions[1:] == ["a", "b"]


def test_invalid_check_is_dropped_with_assumption():
    a = LlmAnalysis(conditions=[{'type': 'sequence', 'text': 'x', 'must_pass': True, 'signals': ['START'], 'check': {'pattern': 'self_hold', 'start': 'NOPE', 'stop': 'START', 'output': 'MOTOR'}}])
    req = analyzer.finalize(project(), a)
    assert req.conditions[0].check is None
    assert any('NOPE' in x for x in req.assumptions)



def test_estop_condition_written_by_name_is_not_duplicated():
    a = LlmAnalysis(conditions=[{'type': 'safety', 'text': 'x', 'must_pass': True, 'signals': ['EMG']}])
    req = analyzer.finalize(project(), a)
    assert len(req.conditions) == 1


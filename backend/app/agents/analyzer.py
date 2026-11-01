"""분석 결과 마무리: Copilot Studio 분석 에이전트가 낸 요구사항을 백엔드가 점검·보완한다.

AI가 판단한 내용을 그대로 믿지 않고 코드로 다시 확인한다(I/O 목록에 없는 신호, 비상정지 조건).
"""
from ..schemas import ProjectInput
from .schemas import Condition, LlmAnalysis, StructuredRequirements

# 시간·정도가 정해지지 않은 모호한 표현. 숫자(예: 3초)가 함께 있으면 모호하지 않다고 본다.
VAGUE_WORDS = ("잠시", "잠깐", "적당히", "적당한", "조금", "나중에", "빨리", "천천히", "어느 정도", "가끔", "대충", "일정 시간")


def _known(p: ProjectInput) -> set[str]:
    known = set()
    for r in p.io_list:
        known.add(r.device.strip().upper())
        known.add(r.name.strip().upper())
    known.discard("")
    return known


def vague_questions(project: ProjectInput) -> list[str]:
    out = []
    for i, c in enumerate(project.conditions):
        word = next((w for w in VAGUE_WORDS if w in c.text), None)
        if word and not any(ch.isdigit() for ch in c.text):
            out.append(f"조건 {c.id or f'C{i + 1}'}의 '{word}'는 구체적으로 얼마나(몇 초 등) 인가요?")
    return out


def finalize(project: ProjectInput, analysis: LlmAnalysis, answers: list[dict] | None = None) -> StructuredRequirements:
    answers = answers or []
    answered = {a["question"] for a in answers}
    conditions = [c.model_copy(update={"id": f"C{i + 1}"}) for i, c in enumerate(analysis.conditions)]
    assumptions = list(analysis.assumptions) + [f"사용자 답변: {a['question']} → {a['answer']}" for a in answers]
    questions = list(analysis.questions) + vague_questions(project)

    known = _known(project)
    for c in conditions:
        missing = [s for s in c.signals if s.strip().upper() not in known]
        if missing:
            questions.append(f"조건 {c.id}에 쓰인 신호 {', '.join(missing)}가 I/O 목록에 없어요. 어떤 디바이스인가요?")

    es = project.plc_config.emergency_stop
    if es.used:
        dev = es.device.strip().upper()
        if not any(c.type == "safety" and dev in {s.strip().upper() for s in c.signals} for c in conditions):
            conditions.append(
                Condition(
                    id=f"C{len(conditions) + 1}", type="safety", must_pass=True, signals=[dev],
                    text=f"비상정지({dev}) 입력 시 모든 출력을 OFF 한다.",
                )
            )
            assumptions.append("비상정지 조건은 입력 설정에 따라 자동으로 추가했어요.")

    return StructuredRequirements(
        plc_config=project.plc_config,
        io_list=project.io_list,
        conditions=conditions,
        timers=analysis.timers,
        counters=analysis.counters,
        assumptions=assumptions,
        questions=[q for q in dict.fromkeys(questions) if q not in answered],
    )

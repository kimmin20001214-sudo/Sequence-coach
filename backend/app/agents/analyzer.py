"""분석 결과 마무리: Copilot Studio 분석 에이전트가 낸 요구사항을 백엔드가 점검·보완한다.

AI가 판단한 내용을 그대로 믿지 않고 코드로 다시 확인한다(I/O 목록에 없는 신호, 비상정지 조건).
"""
from ..schemas import ProjectInput
from .schemas import Condition, LlmAnalysis, StructuredRequirements


def _known(p: ProjectInput) -> set[str]:
    known = set()
    for r in p.io_list:
        known.add(r.device.strip().upper())
        known.add(r.name.strip().upper())
    known.discard("")
    return known


def finalize(project: ProjectInput, analysis: LlmAnalysis) -> StructuredRequirements:
    conditions = [c.model_copy(update={"id": f"C{i + 1}"}) for i, c in enumerate(analysis.conditions)]
    assumptions = list(analysis.assumptions)
    questions = list(analysis.questions)

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
        questions=list(dict.fromkeys(questions)),
    )

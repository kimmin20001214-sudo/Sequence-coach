"""분석 에이전트: 자연어 동작 조건 → 검증 가능한 구조(StructuredRequirements)."""
import json

from pydantic import ValidationError

from ..schemas import ProjectInput
from .llm import call_llm
from .schemas import Condition, LlmAnalysis, StructuredRequirements

MAX_TRIES = 2


def _prompt(p: ProjectInput) -> str:
    cfg = p.plc_config
    return (
        "당신은 MELSEC PLC 제어 요구사항 분석가입니다. 아래 동작 조건을 검증 가능한 조건 목록으로 나누세요.\n"
        "- type은 sequence|interlock|timing|safety|alarm 중 하나\n"
        "- 각 조건의 signals에는 그 조건이 쓰는 신호의 디바이스(예: X1) 또는 이름(예: START)만 적기\n"
        "- 타이머/카운터가 필요하면 timers/counters에 적고, 추측한 내용은 assumptions에 적기\n"
        "- 모호하거나 I/O 목록에 없는 신호가 필요하면 questions에 사용자에게 물을 질문을 적기\n"
        f"PLC: {cfg.series} {cfg.cpu}, 제어 대상: {cfg.control_target}, 타이머 단위: {cfg.timer_unit_ms}ms\n"
        f"I/O 목록: {json.dumps([r.model_dump() for r in p.io_list], ensure_ascii=False)}\n"
        "동작 조건:\n" + "\n".join(f"- {c.text}" for c in p.conditions if c.text.strip())
    )


def _known(p: ProjectInput) -> set[str]:
    known = set()
    for r in p.io_list:
        known.add(r.device.strip().upper())
        known.add(r.name.strip().upper())
    known.discard("")
    return known


def analyze(project: ProjectInput) -> StructuredRequirements:
    schema = LlmAnalysis.model_json_schema()
    prompt = _prompt(project)
    last_err: Exception | None = None
    for _ in range(MAX_TRIES):
        try:
            llm = LlmAnalysis.model_validate(call_llm(prompt, schema))
            break
        except ValidationError as e:
            last_err = e
            prompt += f"\n\n이전 출력이 형식에 맞지 않았어요. 다시 JSON Schema에 맞게 출력하세요: {e.errors()[:3]}"
    else:
        raise ValueError(f"분석 결과 형식이 올바르지 않아요: {last_err}")

    conditions = [c.model_copy(update={"id": f"C{i + 1}"}) for i, c in enumerate(llm.conditions)]
    assumptions = list(llm.assumptions)
    questions = list(llm.questions)

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
        timers=llm.timers,
        counters=llm.counters,
        assumptions=assumptions,
        questions=list(dict.fromkeys(questions)),
    )

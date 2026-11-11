"""에이전트를 부르기 전에 규칙으로 걸러내는 사전 검사. AI 호출 없이 바로 끝난다."""
import re

from .spec import is_compatible

_TIME = re.compile(r"(\d+(?:\.\d+)?)\s*(밀리초|ms|초|분)", re.IGNORECASE)
_UNIT_MS = {"밀리초": 1, "ms": 1, "초": 1000, "분": 60000}
_MAX_K = 32767


def check(project: dict) -> list[str]:
    """실행을 막아야 하는 문제를 한국어 문장으로 돌려준다. 비어 있으면 통과."""
    cfg = project.get("plc_config") or {}
    problems: list[str] = []

    if cfg.get("series") != "Q" or not is_compatible(
        cfg.get("series", ""), cfg.get("cpu", ""), cfg.get("language", ""), cfg.get("software", "")
    ):
        problems.append(
            "지금은 Q시리즈 + 래더 + GX Works2(또는 GX Developer)만 설계할 수 있어요. "
            "1단계에서 시리즈·CPU·소프트웨어를 Q시리즈 기준으로 바꿔 주세요."
        )

    unit = cfg.get("timer_unit_ms", 100)
    if unit != 100:
        problems.append("타이머 단위는 100ms만 지원해요. 1단계에서 타이머 단위를 100ms로 바꿔 주세요.")
        return problems

    for cond in project.get("conditions") or []:
        for value, word in _TIME.findall(cond.get("text", "")):
            ms = float(value) * _UNIT_MS[word.lower()]
            if ms % unit:
                problems.append(
                    f"'{value}{word}'은 타이머 단위({unit}ms)로 나누어떨어지지 않아요. "
                    f"{unit}ms의 배수(예: 0.1초 단위)로 바꿔 주세요."
                )
            elif ms // unit > _MAX_K:
                problems.append(f"'{value}{word}'은 타이머 최대값(K{_MAX_K}, 약 {_MAX_K * unit / 1000:.0f}초)을 넘어요.")
    return problems

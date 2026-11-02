"""Windows 워커 공통: 단계 결과와 재시도."""
from dataclasses import dataclass, field
from typing import Callable, Literal

StepStatus = Literal["completed", "failed", "not_run"]
MAX_ATTEMPTS = 3  # 최초 1회 + 재시도 2회


@dataclass
class StepResult:
    status: StepStatus
    detail: str = ""
    path: str = ""
    logs: list[str] = field(default_factory=list)


def with_retry(action: Callable[[], StepResult], attempts: int = MAX_ATTEMPTS) -> StepResult:
    """not_run(도구 없음)은 재시도해도 같으므로 바로 돌려준다. 예외는 사유를 남기고 앱을 멈추지 않는다."""
    logs: list[str] = []
    result = StepResult("failed", "실행하지 못했어요.")
    for n in range(1, attempts + 1):
        try:
            result = action()
        except Exception as e:  # noqa: BLE001 - 워커 실패가 앱을 멈추면 안 된다
            result = StepResult("failed", f"{type(e).__name__}: {e}")
        logs.append(f"시도 {n}: {result.status} {result.detail}".rstrip())
        if result.status != "failed":
            break
    result.logs = logs + result.logs
    return result

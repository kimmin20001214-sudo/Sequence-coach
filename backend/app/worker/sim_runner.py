"""GX Simulator를 시작하고 시나리오 steps대로 디바이스를 조작한다.

PoC 전에는 실제 시뮬레이터 조작 방법을 알 수 없으므로 not_run을 돌려준다.
"""
from dataclasses import dataclass

from .common import StepResult
from .gx_automation import available


@dataclass
class ScenarioStep:
    device: str
    value: bool
    description: str


def describe(steps: list[ScenarioStep]) -> list[str]:
    """영상 자막에 쓸 단계 설명."""
    return [s.description or f"{s.device} {'ON' if s.value else 'OFF'}" for s in steps]


def run_scenario(steps: list[ScenarioStep]) -> StepResult:
    if not available():
        return StepResult("not_run", "Windows와 pywinauto, GX Simulator가 필요해요. PoC 확인 후 구현해요.")
    return StepResult("not_run", "시뮬레이터 조작은 PoC 결과를 확인한 뒤 구현해요.")

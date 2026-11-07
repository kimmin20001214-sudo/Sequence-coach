"""에이전트가 API로 보내는 분석 결과 모양. 팀 공통 계약 모델은 app/contracts.py에 있다."""
from pydantic import BaseModel, Field

from ..contracts import Check, Condition, CounterSpec, StructuredRequirements, TimerSpec  # noqa: F401


class LlmAnalysis(BaseModel):
    """분석 에이전트(Copilot Studio)가 API로 보내야 하는 JSON 모양."""

    conditions: list[Condition] = Field(default=[], max_length=200)
    timers: list[TimerSpec] = Field(default=[], max_length=100)
    counters: list[CounterSpec] = Field(default=[], max_length=100)
    assumptions: list[str] = Field(default=[], max_length=100)
    questions: list[str] = Field(default=[], max_length=50)
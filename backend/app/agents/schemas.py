"""에이전트 사이를 오가는 구조화 데이터."""
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import IoRow, PlcConfig

ConditionType = Literal["sequence", "interlock", "timing", "safety", "alarm"]


class Condition(BaseModel):
    id: str = ""
    type: ConditionType
    text: str
    must_pass: bool = True
    signals: list[str] = []


class TimerSpec(BaseModel):
    name: str
    preset_ms: int = Field(ge=0)
    purpose: str = ""


class CounterSpec(BaseModel):
    name: str
    preset: int = Field(ge=0)
    purpose: str = ""


class StructuredRequirements(BaseModel):
    plc_config: PlcConfig
    io_list: list[IoRow]
    conditions: list[Condition]
    timers: list[TimerSpec] = []
    counters: list[CounterSpec] = []
    assumptions: list[str] = []
    questions: list[str] = []


class LlmAnalysis(BaseModel):
    """분석 에이전트(Copilot Studio)가 API로 보내야 하는 JSON 모양."""

    conditions: list[Condition] = Field(default=[], max_length=200)
    timers: list[TimerSpec] = Field(default=[], max_length=100)
    counters: list[CounterSpec] = Field(default=[], max_length=100)
    assumptions: list[str] = Field(default=[], max_length=100)
    questions: list[str] = Field(default=[], max_length=50)

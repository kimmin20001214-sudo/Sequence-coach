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
    """LLM이 돌려줘야 하는 JSON 모양."""

    conditions: list[Condition] = []
    timers: list[TimerSpec] = []
    counters: list[CounterSpec] = []
    assumptions: list[str] = []
    questions: list[str] = []

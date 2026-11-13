"""팀 공통 계약(contract): 구현 사이에서 주고받는 데이터 형식.

#40 분석 → StructuredRequirements → #41 설계 → Ir → #42 검증 → VerificationResult → #43 수정 → 다시 Ir
바꾸려면 PR 제목에 [계약 변경]을 붙이고 모든 담당자를 리뷰어로 지정한다. (#53 규칙 5)
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import IoRow, PlcConfig

# ── 작업 상태(state) ────────────────────────────────────────────
JOB_TRANSITIONS: dict[str, set[str]] = {
    "INPUT_VALIDATED": {"ANALYZING"},
    "ANALYZING": {"DESIGNING", "NEEDS_INPUT", "FAILED"},
    "NEEDS_INPUT": set(),
    "DESIGNING": {"VERIFYING", "FAILED"},
    "VERIFYING": {"COMPLETED", "FIXING", "ESCALATED"},
    "FIXING": {"VERIFYING"},
    "COMPLETED": {"GENERATING"},
    "GENERATING": {"DELIVERED", "FAILED"},
    "DELIVERED": set(),
    "ESCALATED": set(),
    "FAILED": set(),
}
JOB_STATES = tuple(JOB_TRANSITIONS)

# ── 분석 결과: StructuredRequirements (#40 → #41) ───────────────
ConditionType = Literal["sequence", "interlock", "timing", "safety", "alarm"]

# 시험 틀(check): 분석 에이전트는 틀 이름과 신호 이름만 고르고, 시험 대본은 코드가 만든다. (#42)
CheckPattern = Literal[
    "self_hold", "stop_priority", "on_delay", "timed_on", "interlock",
    "and_enable", "or_enable", "indicator", "set_reset", "custom",
]


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: CheckPattern
    start: str = ""
    stop: str = ""
    output: str = ""
    outputs: list[str] = []
    trigger: str = ""
    inputs: list[str] = []
    delay_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    a: str = ""
    b: str = ""
    lamp: str = ""
    set_input: str = ""
    reset_input: str = ""
    steps: list[dict] = []
    expect: list[dict] = []


class Condition(BaseModel):
    id: str = ""
    type: ConditionType
    text: str
    must_pass: bool = True
    signals: list[str] = []
    check: Check | None = None


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


# ── 회로 IR (#41 → #42·#44) ─────────────────────────────────────
# 접점 NO/NC, 직렬 AND, 병렬 OR, 출력 OUT/SET/RST/TON/CTU.
# 접점의 NO/NC는 "래더 접점 종류"(a접점/b접점)다. 푸시버튼은 io_list 종류대로 접점을 쓴다: NO(a접점)→NO 접점,
# NC(b접점)→NC 접점(이름은 보지 않는다). 푸시버튼은 누르면 ON으로 시험하므로 GX Simulator2에서도 먼저 ON으로 둘 필요가 없다.
class Contact(BaseModel):
    type: Literal["contact"] = "contact"
    kind: Literal["NO", "NC"]
    signal: str = Field(min_length=1, description="디바이스 주소(X1) 또는 I/O 이름(START)")


class Series(BaseModel):
    type: Literal["AND"] = "AND"
    items: list["Node"] = Field(min_length=1)


class Parallel(BaseModel):
    type: Literal["OR"] = "OR"
    items: list["Node"] = Field(min_length=1)


Node = Annotated[Union[Contact, Series, Parallel], Field(discriminator="type")]
Series.model_rebuild()
Parallel.model_rebuild()


class Output(BaseModel):
    kind: Literal["OUT", "SET", "RST", "TON", "CTU"]
    target: str = Field(min_length=1)
    preset_ms: int | None = Field(default=None, ge=0, description="TON일 때 설정시간(ms)")
    preset: int | None = Field(default=None, ge=0, description="CTU일 때 설정값")

    @model_validator(mode="after")
    def check_preset(self):
        if self.kind == "TON" and self.preset_ms is None:
            raise ValueError("TON에는 preset_ms가 필요해요.")
        if self.kind == "CTU" and self.preset is None:
            raise ValueError("CTU에는 preset이 필요해요.")
        return self


class Rung(BaseModel):
    id: str = Field(min_length=1)
    comment: str = ""
    condition: Node
    outputs: list[Output] = Field(min_length=1)
    covers: list[str] = Field(default=[], description="이 렁이 만족시키는 조건 id 목록")


class Ir(BaseModel):
    version: Literal[1] = 1
    rungs: list[Rung] = Field(min_length=1)


# ── 검증 결과: VerificationResult (#42 → #43) ───────────────────
class VerificationIssue(BaseModel):
    code: str = Field(min_length=1, description="오류 종류 코드. 예: UNKNOWN_SIGNAL, DOUBLE_COIL, UNMET_CONDITION")
    message: str = Field(min_length=1)
    rung_id: str = Field(default="", description="문제가 있는 렁 id. 회로 전체 문제면 빈 값")
    condition_id: str = Field(default="", description="관련 조건 id")


class VerificationResult(BaseModel):
    passed: bool
    errors: list[VerificationIssue] = []
    warnings: list[VerificationIssue] = []

    @model_validator(mode="after")
    def passed_matches_errors(self):
        if self.passed == bool(self.errors):
            raise ValueError("passed는 errors가 비어 있을 때만 true여야 해요.")
        return self

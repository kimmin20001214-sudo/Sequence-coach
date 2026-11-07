"""손으로 작성한 검사 시나리오의 로컬 형식. 팀 공통 계약은 변경하지 않는다."""
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .sim import Bit, InputStep


class Expectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: StrictInt = Field(ge=0)
    dev: str = Field(min_length=1)
    value: Bit

    @field_validator("dev")
    @classmethod
    def nonblank_device(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("기대값을 검사할 신호가 비어 있어요.")
        return value


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition_id: str = Field(min_length=1)
    steps: list[InputStep]
    expect: list[Expectation] = Field(min_length=1)

    @field_validator("condition_id")
    @classmethod
    def nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("조건 ID가 비어 있어요.")
        return value

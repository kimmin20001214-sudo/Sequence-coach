"""검사 시나리오의 로컬 형식(손으로 작성하거나 check 틀에서 코드가 생성)."""
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

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
    expect: list[Expectation] = []
    # 모든 스캔에서 두 신호가 동시에 1이면 안 되는 쌍(인터록)
    exclusive: list[list[str]] = []
    # [원본, 따르는 신호]: 원본이 3스캔 이상 안정되면 따르는 신호가 같아야 함(표시등)
    follow: list[list[str]] = []

    @model_validator(mode="after")
    def has_expectation(self):
        if not (self.expect or self.exclusive or self.follow):
            raise ValueError("기대값(expect)·동시 금지(exclusive)·동기(follow) 중 하나는 필요해요.")
        if any(len(pair) != 2 for pair in self.exclusive + self.follow):
            raise ValueError("exclusive·follow는 신호 두 개씩 짝으로 적어야 해요.")
        return self

    @field_validator("condition_id")
    @classmethod
    def nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("조건 ID가 비어 있어요.")
        return value

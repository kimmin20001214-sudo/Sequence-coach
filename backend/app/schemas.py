"""입력 JSON 구조. 의미 검증(호환성·점수·디바이스)은 validation.py에서 한다."""
from pydantic import BaseModel, Field, field_validator


class EmergencyStop(BaseModel):
    used: bool = False
    device: str = ""


class DeviceRule(BaseModel):
    M: int = 0
    D: int = 0
    T: int = 0
    C: int = 0


class PlcConfig(BaseModel):
    series: str = ""
    cpu: str = ""
    language: str = ""
    software: str = ""
    x_points: int | None = None
    y_points: int | None = None
    control_target: str = ""
    safety_ack: bool = False
    emergency_stop: EmergencyStop = Field(default_factory=EmergencyStop)
    modules: list[str] = []
    device_rule: DeviceRule = Field(default_factory=DeviceRule)
    timer_unit_ms: int = 100
    modes: list[str] = ["자동"]
    retentive: bool = False
    alarm: bool = False
    project_name: str = ""
    comment_lang: str = "ko"
    note: str = ""


class IoRow(BaseModel):
    device: str = ""
    name: str = ""
    kind: str = ""
    desc: str = ""


class Condition(BaseModel):
    id: str = ""
    text: str = ""
    must_pass: bool = True


class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    payload: dict

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("이름을 입력해 주세요.")
        return v

    @field_validator("payload")
    @classmethod
    def limit_size(cls, v: dict) -> dict:
        cfg, conds = v.get("config"), v.get("conditions")
        if not isinstance(cfg, dict) or not isinstance(conds, list):
            raise ValueError("템플릿에는 설정(config)과 조건(conditions) 목록이 있어야 해요.")
        if not all(isinstance(c, dict) and isinstance(c.get("text", ""), str) for c in conds):
            raise ValueError("템플릿의 조건 형식이 올바르지 않아요.")
        io = cfg.get("io_list", [])
        if not isinstance(io, list) or not all(isinstance(r, dict) for r in io):
            raise ValueError("템플릿의 입출력 목록 형식이 올바르지 않아요.")
        if len(str(v)) > 200_000 or len(io) > 1000:
            raise ValueError("템플릿이 너무 커요.")
        return v


class ProjectInput(BaseModel):
    plc_config: PlcConfig
    io_list: list[IoRow] = []
    conditions: list[Condition] = []

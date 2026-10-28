"""입력 JSON 구조. 의미 검증(호환성·점수·디바이스)은 validation.py에서 한다."""
from pydantic import BaseModel, Field


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


class ProjectInput(BaseModel):
    plc_config: PlcConfig
    io_list: list[IoRow] = []
    conditions: list[Condition] = []

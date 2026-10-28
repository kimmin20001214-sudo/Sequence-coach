"""프로젝트 입력 검증. 프론트(frontend/src/validate.ts)와 같은 키·메시지를 돌려준다."""
import re

from .schemas import IoRow, ProjectInput
from .spec import get_series, is_compatible, parse_device

_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")


def _notation_label(spec: dict) -> str:
    return "16진수" if spec["notation"] == "hex" else "8진수"


def validate_io_list(rows: list[IoRow], spec: dict | None, cpu: dict | None) -> dict[int, str]:
    errors: dict[int, str] = {}
    seen: set[str] = set()
    for i, row in enumerate(rows):
        dev = row.device.strip().upper()
        if not dev or not row.name.strip():
            errors[i] = "디바이스와 이름을 입력해 주세요."
            continue
        if not spec:
            continue
        parsed = parse_device(dev, spec["notation"])
        if not parsed:
            errors[i] = f"디바이스 형식이 올바르지 않아요. ({_notation_label(spec)} X/Y)"
            continue
        kind, num = parsed
        limit = cpu and (cpu["max_x"] if kind == "X" else cpu["max_y"])
        if limit and num >= limit:
            errors[i] = f"{dev}은(는) {limit}점 범위를 벗어나요."
        elif dev in seen:
            errors[i] = f"{dev}이(가) 중복돼요."
        seen.add(dev)
    return errors


def validate_project(p: ProjectInput) -> dict:
    cfg = p.plc_config
    f: dict[str, str] = {}

    def need(key: str, label: str) -> None:
        if str(getattr(cfg, key) if getattr(cfg, key) is not None else "").strip() == "":
            f[key] = f"{label} 항목을 입력해 주세요."

    need("series", "시리즈")
    need("cpu", "CPU")
    need("language", "프로그램 언어")
    need("software", "GX Works 버전")
    need("x_points", "입력(X) 점수")
    need("y_points", "출력(Y) 점수")
    need("control_target", "제어 대상 유형")
    if not cfg.safety_ack:
        f["safety_ack"] = "안전 고지에 동의해야 진행할 수 있어요."

    spec = get_series(cfg.series)
    cpu = spec["cpus"].get(cfg.cpu) if spec else None
    if cfg.series and cfg.cpu and cfg.language and cfg.software and "cpu" not in f:
        if not is_compatible(cfg.series, cfg.cpu, cfg.language, cfg.software):
            f["compat"] = "선택한 시리즈·CPU·언어·GX Works 버전은 함께 사용할 수 없어요."

    for key, limit, label in (
        ("x_points", cpu and cpu["max_x"], "입력(X) 점수"),
        ("y_points", cpu and cpu["max_y"], "출력(Y) 점수"),
    ):
        if key in f:
            continue
        n = getattr(cfg, key)
        if n < 0:
            f[key] = f"{label}는 0 이상의 정수여야 해요."
        elif limit and n > limit:
            f[key] = f"{label}는 {cfg.cpu}의 최대 {limit}점을 넘을 수 없어요."

    if cfg.emergency_stop.used:
        dev = cfg.emergency_stop.device.strip()
        if not dev:
            f["emergency_stop"] = "비상정지 입력 디바이스를 입력해 주세요."
        elif spec and not parse_device(dev, spec["notation"]):
            f["emergency_stop"] = f"디바이스 형식이 올바르지 않아요. ({_notation_label(spec)} X/Y)"

    if not p.io_list:
        f["io_empty"] = "입출력 신호를 1개 이상 입력해 주세요."
    io = validate_io_list(p.io_list, spec, cpu)

    if cfg.project_name and not _NAME_RE.match(cfg.project_name):
        f["project_name"] = "프로젝트 이름은 영문·숫자·_ 로 최대 32자예요."

    texts = [c for c in p.conditions if c.text.strip()]
    if not texts:
        f["conditions"] = "동작 조건을 1개 이상 입력해 주세요."
    elif not any(c.must_pass for c in texts):
        f["conditions"] = "필수 조건을 1개 이상 지정해 주세요."

    return {"fields": f, "io": io}


def has_errors(result: dict) -> bool:
    return bool(result["fields"] or result["io"])

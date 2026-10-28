"""PLC 기준 데이터 로딩과 호환성·디바이스 규칙. 프론트 검증과 같은 규칙을 서버에서도 적용한다."""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@lru_cache
def load_spec() -> dict:
    return json.loads((DATA_DIR / "plc_spec.json").read_text(encoding="utf-8"))


@lru_cache
def load_instructions() -> dict:
    return json.loads((DATA_DIR / "instructions.json").read_text(encoding="utf-8"))


def get_series(series: str) -> dict | None:
    return load_spec()["series"].get(series)


def is_compatible(series: str, cpu: str, language: str, software: str) -> bool:
    s = get_series(series)
    return bool(s) and cpu in s["cpus"] and language in s["languages"] and software in s["software"]


_DEVICE_RE = {
    "hex": re.compile(r"^([XY])([0-9A-F]+)$", re.I),
    "octal": re.compile(r"^([XY])([0-7]+)$", re.I),
}


def parse_device(text: str, notation: str) -> tuple[str, int] | None:
    """'X1F' -> ('X', 31) (hex), 'X17' -> ('X', 15) (octal). 형식이 틀리면 None."""
    m = _DEVICE_RE[notation].match(text.strip())
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2), 16 if notation == "hex" else 8)

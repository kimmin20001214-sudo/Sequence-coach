"""GX Works UI 자동화(프로젝트 생성·가져오기·저장·컴파일).

PoC(docs/poc-gxworks.md) 전에는 실제 동작을 알 수 없어 구현하지 않는다.
설치되지 않은 환경에서는 성공을 꾸미지 않고 not_run을 돌려준다.
"""
import importlib.util
import os
from pathlib import Path

from .common import StepResult


def available() -> bool:
    return os.name == "nt" and importlib.util.find_spec("pywinauto") is not None


def import_and_compile(il_file: Path, project_dir: Path) -> StepResult:
    if not available():
        return StepResult("not_run", "Windows와 pywinauto, GX Works가 필요해요. PoC 확인 후 구현해요.")
    return StepResult("not_run", "GX Works 자동화는 PoC 결과를 확인한 뒤 구현해요.")

"""공용 Ir를 검사한 뒤 Q 래더 명령어 목록으로 변환한다."""
from collections.abc import Mapping

from ..contracts import Ir, VerificationResult
from ..schemas import IoRow, PlcConfig
from .rules import _check_and_compile


class IrConversionError(ValueError):
    """부분 명령어를 반환하지 않고 공용 형식의 오류를 제공한다."""

    def __init__(self, result: VerificationResult):
        self.result = result
        super().__init__("; ".join(issue.message for issue in result.errors))


def to_il(
    ir: Ir,
    config: PlcConfig,
    io_list: list[IoRow],
    *,
    internal_limits: Mapping[str, int] | None = None,
) -> list[str]:
    """실패하면 IrConversionError, 성공하면 END를 포함한 명령어 목록을 반환한다."""
    result, lines = _check_and_compile(ir, config, io_list, internal_limits)
    if not result.passed:
        raise IrConversionError(result)
    return lines

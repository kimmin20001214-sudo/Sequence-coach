"""명령어·등록 I/O·호출자가 지정한 내부 주소 범위를 검사한다."""
import re
from collections.abc import Mapping

from ..contracts import Contact, Ir, Node, VerificationIssue, VerificationResult
from ..schemas import IoRow, PlcConfig
from ..spec import get_series, is_compatible, load_instructions, parse_device
from ..validation import validate_io_list
from ._compiler import compile_ir

_INTERNAL = re.compile(r"^([MDTC])([0-9]+)$")


def _check_and_compile(
    ir: Ir,
    config: PlcConfig,
    io_list: list[IoRow],
    internal_limits: Mapping[str, int] | None,
) -> tuple[VerificationResult, list[str]]:
    errors: list[VerificationIssue] = []
    warnings = [VerificationIssue(
        code="EXPERT_REVIEW_REQUIRED",
        message="사전 규칙 검사만 수행해요. 실제 설비 적용 전 전문가 확인이 필요해요.",
    )]

    def error(code: str, message: str, rung_id: str = "") -> None:
        errors.append(VerificationIssue(code=code, message=message, rung_id=rung_id))

    def result(lines: list[str] | None = None) -> tuple[VerificationResult, list[str]]:
        return VerificationResult(passed=not errors, errors=errors, warnings=warnings), lines or []

    spec = get_series(config.series)
    if config.series != "Q" or config.language != "ladder" or not is_compatible(
        config.series, config.cpu, config.language, config.software
    ):
        error("UNSUPPORTED_CONFIG", "Q시리즈의 호환 CPU·GX Works2/GX Developer·래더 설정만 지원해요.")
        return result()
    assert spec is not None
    cpu = spec["cpus"][config.cpu]
    if not cpu["verified"]:
        warnings.append(VerificationIssue(
            code="UNVERIFIED_CPU_LIMITS", message="CPU 입출력 점수는 매뉴얼 미확인 임시값이에요.",
        ))
    for kind, points in (("X", config.x_points), ("Y", config.y_points)):
        if points is None or not 0 <= points <= cpu[f"max_{kind.lower()}"]:
            error("INVALID_IO_POINTS", f"{kind} 점수는 기준 데이터 이내의 0 이상 값이 필요해요.")
    if type(config.timer_unit_ms) is not int or config.timer_unit_ms != 100:
        error("UNSUPPORTED_TIMER_UNIT", "Q 타이머 초안은 100ms 단위만 지원해요. 10ms·1ms는 매뉴얼 확인이 필요해요.")

    limits = internal_limits if internal_limits is not None else {}
    starts = config.device_rule.model_dump()
    for kind, start in starts.items():
        if type(start) is not int or start < 0:
            error("INVALID_INTERNAL_RANGE", f"{kind} 시작 번호는 0 이상 정수여야 해요.")
    for kind, end in limits.items():
        if kind not in starts or type(end) is not int or not 0 <= starts[kind] < end:
            error("INVALID_INTERNAL_RANGE", "내부 주소 끝값은 M/D/T/C별 시작 번호보다 큰 정수여야 해요.")

    for index, message in validate_io_list(io_list, spec, cpu).items():
        error("INVALID_IO_LIST", f"I/O {index + 1}행: {message}")

    def address(text: str) -> str | None:
        text = text.strip().upper()
        parsed = parse_device(text, spec["notation"])
        if parsed:
            return f"{parsed[0]}{parsed[1]:X}"
        internal = _INTERNAL.fullmatch(text)
        return f"{internal[1]}{int(internal[2])}" if internal else None

    registered: set[str] = set()
    aliases: dict[str, str] = {}
    for row in io_list:
        dev = address(row.device)
        if dev is None or dev[0] not in "XY":
            continue
        if dev in registered:
            error("DUPLICATE_IO", f"{dev} 주소가 중복돼요.")
        registered.add(dev)
        points = config.x_points if dev[0] == "X" else config.y_points
        if points is not None and int(dev[1:], 16) >= points:
            error("IO_OUT_OF_RANGE", f"{dev} 주소가 설정한 I/O 점수를 벗어나요.")
        for token in (row.device.strip().upper(), row.name.strip().upper()):
            direct = address(token)
            if (direct is not None and direct != dev) or (token in aliases and aliases[token] != dev):
                error("AMBIGUOUS_SIGNAL", f"{token} 이름과 주소를 하나의 신호로 구분할 수 없어요.")
            aliases[token] = dev
    if errors:
        return result()

    def resolve(text: str, rung_id: str) -> str | None:
        token = text.strip().upper()
        dev = aliases.get(token) or address(token)
        if dev is None:
            error("UNKNOWN_SIGNAL", f"{text} 신호를 찾을 수 없어요.", rung_id)
        elif dev[0] in "XY":
            if dev not in registered:
                error("UNREGISTERED_IO", f"{dev} 주소가 I/O 목록에 없어요.", rung_id)
            else:
                return dev
        else:
            kind, number = dev[0], int(dev[1:])
            if kind not in limits:
                error("INTERNAL_RANGE_REQUIRED", f"{kind} 내부 주소의 허용 끝값을 지정해 주세요.", rung_id)
            elif not starts[kind] <= number < limits[kind]:
                error("INTERNAL_OUT_OF_RANGE", f"{dev} 주소가 설정한 시작 번호·끝값 범위를 벗어나요.", rung_id)
            else:
                return dev
        return None

    resolved = ir.model_copy(deep=True)

    def visit(node: Node, rung_id: str) -> None:
        if isinstance(node, Contact):
            dev = resolve(node.signal, rung_id)
            if dev is not None:
                node.signal = dev
                if dev[0] == "D":
                    error("UNSUPPORTED_DEVICE", "D 워드는 비트 접점으로 지원하지 않아요.", rung_id)
        else:
            for child in node.items:
                visit(child, rung_id)

    seen_rungs: set[str] = set()
    for rung in resolved.rungs:
        if rung.id in seen_rungs:
            error("DUPLICATE_RUNG", "렁 id가 중복돼요.", rung.id)
        seen_rungs.add(rung.id)
        visit(rung.condition, rung.id)
        for output in rung.outputs:
            dev = resolve(output.target, rung.id)
            if dev is not None:
                output.target = dev
                allowed_devices = {"TON": "T", "CTU": "C"}.get(output.kind, "YM")
                if dev[0] not in allowed_devices:
                    error("INVALID_OUTPUT_DEVICE", f"{output.kind} 출력에 {dev} 주소를 사용할 수 없어요.", rung.id)
            if output.kind == "TON":
                preset = output.preset_ms
                if preset is None or preset % config.timer_unit_ms or not 1 <= preset // config.timer_unit_ms <= 32767:
                    error("INVALID_TIMER_PRESET", "타이머는 100ms의 배수이며 K1~K32767로 정확히 표현돼야 해요.", rung.id)
                if output.preset is not None:
                    error("UNEXPECTED_PRESET", "TON에는 preset 대신 preset_ms만 사용해 주세요.", rung.id)
            elif output.kind == "CTU":
                if output.preset is None or not 1 <= output.preset <= 32767:
                    error("INVALID_COUNTER_PRESET", "카운터 설정값은 K1~K32767만 지원해요.", rung.id)
                if output.preset_ms is not None:
                    error("UNEXPECTED_PRESET", "CTU에는 preset_ms 대신 preset만 사용해 주세요.", rung.id)
            elif output.preset is not None or output.preset_ms is not None:
                error("UNEXPECTED_PRESET", "일반 코일에는 시간·카운터 설정값을 사용할 수 없어요.", rung.id)
    if errors:
        return result()

    allowed = set(load_instructions()["series"].get(config.series, []))
    lines: list[str] = []
    for key, line in compile_ir(resolved, config):
        if key not in allowed or line.split()[0] not in allowed:
            error("DISALLOWED_INSTRUCTION", f"{key} 명령어는 시리즈 허용목록에 없어요.")
        lines.append(line)
    return result(lines if not errors else None)


def validate_ir(
    ir: Ir,
    config: PlcConfig,
    io_list: list[IoRow],
    *,
    internal_limits: Mapping[str, int] | None = None,
) -> VerificationResult:
    """끝값 미포함 범위 [device_rule 시작, internal_limits 끝)로 사전 검사한다."""
    result, _ = _check_and_compile(ir, config, io_list, internal_limits)
    return result

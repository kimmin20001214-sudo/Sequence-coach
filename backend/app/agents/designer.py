"""Studio 설계 에이전트가 사용하는 제한된 자기유지 초안 생성 도구."""

from ..contracts import Contact, Node, StructuredRequirements
from ..plc.self_hold import design_self_hold

SAFETY_NOTICE = "설계 초안이며 안전 검토·시뮬레이션을 수행하지 않았어요. 실제 설비 적용 전 전문가 확인 필요."


def create_draft(req: StructuredRequirements) -> dict:
    if req.plc_config.series != "Q":
        raise ValueError("이번 설계 도구는 MELSEC Q시리즈만 지원해요.")
    if req.plc_config.retentive or req.plc_config.alarm or req.plc_config.modes != ["자동"]:
        raise ValueError("정전 유지·알람·운전 모드 전환은 이번 설계 도구에서 지원하지 않아요.")
    ir = design_self_hold(req)
    used = set()

    def collect(node: Node) -> None:
        if isinstance(node, Contact):
            used.add(node.signal)
        else:
            for item in node.items:
                collect(item)

    for rung in ir.rungs:
        collect(rung.condition)
        used.update(output.target for output in rung.outputs)
    return {
        "ir": ir.model_dump(),
        "io_used": [row.model_dump() for row in req.io_list if row.device.strip().upper() in used],
        "explanation": [
            {"rung_id": rung.id, "condition_ids": rung.covers,
             "text": "시작 버튼을 누르면 출력이 켜지고, 손을 떼도 출력 접점으로 유지해요. "
                     "정지 버튼을 누르면 시작 입력보다 우선하여 출력을 꺼요. "
                     "NC 버튼은 평상시 입력이 ON이므로 래더 접점과 물리 버튼 종류를 구분해요."}
            for rung in ir.rungs
        ],
        "assumptions": req.assumptions,
        "limitations": [
            "START/STOP/MOTOR 자기유지·정지 조건 한 쌍만 지원해요. 임의 자연어 논리의 정확성은 검증하지 않았어요.",
            "타이머·카운터·비상정지·ST·내부 주소 할당·IL 변환·GX Works 파일 생성은 미지원이에요.",
            "CPU별 점수는 기준 데이터의 임시값이며 매뉴얼 검증 완료를 뜻하지 않아요.",
        ],
        "safety_review": "not_run",
        "verification": "not_run",
        "notice": SAFETY_NOTICE,
    }

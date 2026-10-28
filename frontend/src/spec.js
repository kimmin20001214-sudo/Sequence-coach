// 임시 내장 데이터. #38에서 backend의 /meta API로 대체한다.
// max_x / max_y 값은 임시값이므로 Mitsubishi 매뉴얼로 확인이 필요하다.
export const SPEC = {
  "iQ-R": {
    notation: "hex",
    software: ["GX Works3"],
    languages: ["ladder", "st"],
    cpus: Object.fromEntries(
      ["R00CPU", "R01CPU", "R02CPU", "R04CPU", "R08CPU", "R16CPU", "R32CPU", "R120CPU"].map((c) => [
        c,
        { max_x: 4096, max_y: 4096 },
      ])
    ),
  },
  "iQ-F": {
    notation: "octal",
    software: ["GX Works3"],
    languages: ["ladder", "st"],
    cpus: {
      FX5U: { max_x: 256, max_y: 256 },
      FX5UC: { max_x: 256, max_y: 256 },
      FX5UJ: { max_x: 256, max_y: 256 },
    },
  },
};

export const LANGUAGE_LABELS = { ladder: "래더(Ladder)", st: "ST (구조화 텍스트)" };

export const CONTROL_TARGETS = ["컨베이어", "모터 기동·정지", "실린더(공압·유압)", "탱크·레벨", "신호등", "기타"];

export const IO_KINDS = [
  "푸시버튼 NO",
  "푸시버튼 NC",
  "센서",
  "리미트스위치",
  "솔레노이드",
  "모터",
  "램프",
  "기타",
];

export const MODULES = ["아날로그 입력", "아날로그 출력", "고속 카운터", "위치결정", "통신(Ethernet)", "통신(RS-485)"];
export const OPERATION_MODES = ["자동", "수동", "원점복귀", "점검"];

export const SAFETY_NOTICE =
  "완성된 회로는 결코 안전을 보장하지 않으며, 실제 설비 적용 전 전문가의 추가 확인이 필요합니다.";

export type Notation = "hex" | "octal";

export interface CpuSpec {
  max_x: number;
  max_y: number;
}

export interface SeriesSpec {
  notation: Notation;
  software: string[];
  languages: string[];
  cpus: Record<string, CpuSpec>;
}

// 임시 내장 데이터. #38에서 backend의 /meta API로 대체한다.
// max_x / max_y 값은 임시값이므로 Mitsubishi 매뉴얼로 확인이 필요하다.
export const SPEC: Record<string, SeriesSpec> = {
  "iQ-R": {
    notation: "hex",
    software: ["GX Works3"],
    languages: ["ladder", "st"],
    cpus: Object.fromEntries(
      ["R00CPU", "R01CPU", "R02CPU", "R04CPU", "R08CPU", "R16CPU", "R32CPU", "R120CPU"].map((c) => [
        c,
        { max_x: 4096, max_y: 4096 },
      ]),
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

export const LANGUAGE_LABELS: Record<string, string> = { ladder: "래더(Ladder)", st: "ST (구조화 텍스트)" };
export const CONTROL_TARGETS = ["컨베이어", "모터 기동·정지", "실린더(공압·유압)", "탱크·레벨", "신호등", "기타"];
export const IO_KINDS = ["푸시버튼 NO", "푸시버튼 NC", "센서", "리미트스위치", "솔레노이드", "모터", "램프", "기타"];
export const MODULES = ["아날로그 입력", "아날로그 출력", "고속 카운터", "위치결정", "통신(Ethernet)", "통신(RS-485)"];
export const OPERATION_MODES = ["자동", "수동", "원점복귀", "점검"];

export const SAFETY_NOTICE =
  "완성된 회로는 결코 안전을 보장하지 않으며, 실제 설비 적용 전 전문가의 추가 확인이 필요합니다.";

export interface IoRow {
  device: string;
  name: string;
  kind: string;
  desc: string;
}

export interface Config {
  series: string;
  cpu: string;
  language: string;
  software: string;
  x_points: string;
  y_points: string;
  control_target: string;
  safety_ack: boolean;
  emergency_stop: { used: boolean; device: string };
  io_list: IoRow[];
  modules: string[];
  device_rule: { M: number; D: number; T: number; C: number };
  timer_unit_ms: number;
  modes: string[];
  retentive: boolean;
  alarm: boolean;
  project_name: string;
  comment_lang: string;
  note: string;
}

export interface Condition {
  text: string;
  must_pass: boolean;
}

export const emptyRow = (): IoRow => ({ device: "", name: "", kind: IO_KINDS[0], desc: "" });

export const initialConfig = (): Config => ({
  series: "",
  cpu: "",
  language: "",
  software: "",
  x_points: "",
  y_points: "",
  control_target: "",
  safety_ack: false,
  emergency_stop: { used: false, device: "" },
  io_list: [emptyRow()],
  modules: [],
  device_rule: { M: 0, D: 0, T: 0, C: 0 },
  timer_unit_ms: 100,
  modes: ["자동"],
  retentive: false,
  alarm: false,
  project_name: "",
  comment_lang: "ko",
  note: "",
});

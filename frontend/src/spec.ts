export type Notation = "hex" | "octal";

export interface CpuSpec {
  max_x: number;
  max_y: number;
  verified?: boolean;
}

export interface SeriesSpec {
  notation: Notation;
  software: string[];
  languages: string[];
  cpus: Record<string, CpuSpec>;
}

export interface Meta {
  series: Record<string, SeriesSpec>;
  options: {
    language_labels: Record<string, string>;
    control_targets: string[];
    io_kinds: string[];
    modules: string[];
    operation_modes: string[];
  };
  safety_notice: string;
}

// 백엔드 GET /meta 로 채워진다. App이 로딩을 마친 뒤에만 화면을 그리므로 사용 시점엔 항상 채워져 있다.
export let SPEC: Record<string, SeriesSpec> = {};
export let LANGUAGE_LABELS: Record<string, string> = {};
export let CONTROL_TARGETS: string[] = [];
export let IO_KINDS: string[] = [];
export let MODULES: string[] = [];
export let OPERATION_MODES: string[] = [];
export let SAFETY_NOTICE = "";

export function applyMeta(m: Meta) {
  SPEC = m.series;
  LANGUAGE_LABELS = m.options.language_labels;
  CONTROL_TARGETS = m.options.control_targets;
  IO_KINDS = m.options.io_kinds;
  MODULES = m.options.modules;
  OPERATION_MODES = m.options.operation_modes;
  SAFETY_NOTICE = m.safety_notice;
}

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

export const emptyRow = (): IoRow => ({ device: "", name: "", kind: IO_KINDS[0] ?? "", desc: "" });

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

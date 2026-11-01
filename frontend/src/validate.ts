import { SPEC, type Config, type IoRow, type SeriesSpec, type CpuSpec } from "./spec";

export interface ValidationResult {
  fields: Record<string, string>;
  io: Record<number, string>;
}

export function isCompatible(series: string, cpu: string, language: string, software: string): boolean {
  const s = SPEC[series];
  return !!s && cpu in s.cpus && s.languages.includes(language) && s.software.includes(software);
}

// "X1F" -> 31 (hex), "X17" -> 15 (octal). 형식이 맞지 않으면 null
export function parseDevice(text: string, notation: "hex" | "octal") {
  const re = notation === "hex" ? /^([XY])([0-9A-F]+)$/i : /^([XY])([0-7]+)$/i;
  const m = re.exec(text.trim());
  if (!m) return null;
  return { kind: m[1].toUpperCase(), num: parseInt(m[2], notation === "hex" ? 16 : 8) };
}

const notationLabel = (s: SeriesSpec) => (s.notation === "hex" ? "16진수" : "8진수");

export function validateIoList(list: IoRow[], spec?: SeriesSpec, cpu?: CpuSpec): Record<number, string> {
  const errors: Record<number, string> = {};
  const seen = new Set<string>();
  list.forEach((row, i) => {
    const dev = row.device.trim().toUpperCase();
    if (!dev || !row.name.trim()) {
      errors[i] = "디바이스와 이름을 입력해 주세요.";
      return;
    }
    if (!spec) return;
    const p = parseDevice(dev, spec.notation);
    if (!p) {
      errors[i] = `디바이스 형식이 올바르지 않아요. (${notationLabel(spec)} X/Y)`;
      return;
    }
    const max = cpu && (p.kind === "X" ? cpu.max_x : cpu.max_y);
    if (max !== undefined && p.num >= max) errors[i] = `${dev}은(는) ${max}점 범위를 벗어나요.`;
    else if (seen.has(dev)) errors[i] = `${dev}이(가) 중복돼요.`;
    seen.add(dev);
  });
  return errors;
}

export function validateConfig(cfg: Config): ValidationResult {
  const f: Record<string, string> = {};
  const need = (key: keyof Config, label: string) => {
    if (String(cfg[key] ?? "").trim() === "") f[key] = `${label} 항목을 입력해 주세요.`;
  };
  need("series", "시리즈");
  need("cpu", "CPU");
  need("language", "프로그램 언어");
  need("software", "GX Works 버전");
  need("x_points", "입력(X) 점수");
  need("y_points", "출력(Y) 점수");
  need("control_target", "제어 대상 유형");
  if (!cfg.safety_ack) f.safety_ack = "안전 고지에 동의해야 진행할 수 있어요.";

  const spec = SPEC[cfg.series];
  const cpu = spec?.cpus[cfg.cpu];
  if (cfg.series && cfg.cpu && cfg.language && cfg.software && !f.cpu && !isCompatible(cfg.series, cfg.cpu, cfg.language, cfg.software)) {
    f.compat = "선택한 시리즈·CPU·언어·GX Works 버전은 함께 사용할 수 없어요.";
  }
  for (const [key, max, label] of [
    ["x_points", cpu?.max_x, "입력(X) 점수"],
    ["y_points", cpu?.max_y, "출력(Y) 점수"],
  ] as const) {
    if (f[key]) continue;
    const n = Number(cfg[key]);
    if (!Number.isInteger(n) || n < 0) f[key] = `${label}는 0 이상의 정수여야 해요.`;
    else if (max !== undefined && n > max) f[key] = `${label}는 ${cfg.cpu}의 최대 ${max}점을 넘을 수 없어요.`;
  }

  if (cfg.emergency_stop.used) {
    if (!cfg.emergency_stop.device.trim()) f.emergency_stop = "비상정지 입력 디바이스를 입력해 주세요.";
    else if (spec && !parseDevice(cfg.emergency_stop.device, spec.notation))
      f.emergency_stop = `디바이스 형식이 올바르지 않아요. (${notationLabel(spec)} X/Y)`;
  }

  const io = validateIoList(cfg.io_list, spec, cpu);
  if (!cfg.io_list.length) f.io_empty = "입출력 신호를 1개 이상 입력해 주세요.";
  if (cfg.project_name && !/^[A-Za-z0-9_]{1,32}$/.test(cfg.project_name))
    f.project_name = "프로젝트 이름은 영문·숫자·_ 로 최대 32자예요.";
  return { fields: f, io };
}

export const hasErrors = (r: ValidationResult) => Object.keys(r.fields).length > 0 || Object.keys(r.io).length > 0;

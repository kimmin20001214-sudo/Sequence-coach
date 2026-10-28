import { SPEC } from "./spec.js";

export function isCompatible(series, cpu, language, software) {
  const s = SPEC[series];
  return !!s && cpu in s.cpus && s.languages.includes(language) && s.software.includes(software);
}

// "X1F" -> 31 (hex), "X17" -> 15 (octal). 형식이 맞지 않으면 null
export function parseDevice(text, notation) {
  const re = notation === "hex" ? /^([XY])([0-9A-F]+)$/i : /^([XY])([0-7]+)$/i;
  const m = re.exec(String(text).trim());
  if (!m) return null;
  return { kind: m[1].toUpperCase(), num: parseInt(m[2], notation === "hex" ? 16 : 8) };
}

// 반환: { field: message } . 비어 있으면 통과
export function validateConfig(cfg) {
  const errors = {};
  const need = (key, label) => {
    if (cfg[key] === undefined || cfg[key] === null || String(cfg[key]).trim() === "") {
      errors[key] = `${label} 항목을 입력해 주세요.`;
    }
  };
  need("series", "시리즈");
  need("cpu", "CPU");
  need("language", "프로그램 언어");
  need("software", "GX Works 버전");
  need("x_points", "입력(X) 점수");
  need("y_points", "출력(Y) 점수");
  need("control_target", "제어 대상 유형");
  if (!cfg.safety_ack) errors.safety_ack = "안전 고지에 동의해야 진행할 수 있어요.";

  const s = SPEC[cfg.series];
  const cpu = s && s.cpus[cfg.cpu];
  if (cfg.series && cfg.cpu && cfg.language && cfg.software && !errors.cpu) {
    if (!isCompatible(cfg.series, cfg.cpu, cfg.language, cfg.software)) {
      errors.compat = "선택한 시리즈·CPU·언어·GX Works 버전은 함께 사용할 수 없어요.";
    }
  }
  for (const [key, max, label] of [
    ["x_points", cpu && cpu.max_x, "입력(X) 점수"],
    ["y_points", cpu && cpu.max_y, "출력(Y) 점수"],
  ]) {
    if (errors[key] || cfg[key] === undefined || cfg[key] === "") continue;
    const n = Number(cfg[key]);
    if (!Number.isInteger(n) || n < 0) errors[key] = `${label}는 0 이상의 정수여야 해요.`;
    else if (max !== undefined && n > max) errors[key] = `${label}는 ${cfg.cpu}의 최대 ${max}점을 넘을 수 없어요.`;
  }

  if (cfg.emergency_stop && cfg.emergency_stop.used) {
    if (!cfg.emergency_stop.device) errors.emergency_stop = "비상정지 입력 디바이스를 입력해 주세요.";
    else if (s && !parseDevice(cfg.emergency_stop.device, s.notation))
      errors.emergency_stop = `디바이스 형식이 올바르지 않아요. (${s.notation === "hex" ? "16진수" : "8진수"} X/Y)`;
  }

  const ioErrors = validateIoList(cfg.io_list || [], s, cpu);
  if (Object.keys(ioErrors).length) errors.io_list = ioErrors;
  if (!(cfg.io_list || []).length) errors.io_list_empty = "입출력 신호를 1개 이상 입력해 주세요.";

  if (cfg.project_name && !/^[A-Za-z0-9_]{1,32}$/.test(cfg.project_name))
    errors.project_name = "프로젝트 이름은 영문·숫자·_ 로 최대 32자예요.";
  return errors;
}

// 반환: { 행 인덱스: message }
export function validateIoList(list, spec, cpu) {
  const errors = {};
  const seen = new Set();
  list.forEach((row, i) => {
    const dev = String(row.device || "").trim().toUpperCase();
    if (!dev || !String(row.name || "").trim()) {
      errors[i] = "디바이스와 이름을 입력해 주세요.";
      return;
    }
    if (!spec) return;
    const p = parseDevice(dev, spec.notation);
    if (!p) {
      errors[i] = `디바이스 형식이 올바르지 않아요. (${spec.notation === "hex" ? "16진수" : "8진수"} X/Y)`;
      return;
    }
    const max = cpu && (p.kind === "X" ? cpu.max_x : cpu.max_y);
    if (max !== undefined && p.num >= max) errors[i] = `${dev}은(는) ${max}점 범위를 벗어나요.`;
    else if (seen.has(dev)) errors[i] = `${dev}이(가) 중복돼요.`;
    seen.add(dev);
  });
  return errors;
}

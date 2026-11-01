import {
  SPEC, LANGUAGE_LABELS, CONTROL_TARGETS, IO_KINDS, MODULES, OPERATION_MODES, SAFETY_NOTICE, emptyRow, initialConfig,
  type Config, type Condition,
} from "./spec";
import { useRef, useState } from "react";
import type { ValidationResult } from "./validate";
import { Card, Field, Chips, Segmented } from "./ui";
import TemplatesCard from "./TemplatesCard";
import { parseIoCsv, downloadCsvTemplate } from "./csv";

interface Props {
  cfg: Config;
  setCfg: (c: Config) => void;
  conditions: Condition[];
  setConditions: (c: Condition[]) => void;
  result: ValidationResult | null;
  onNext: () => void;
}

export default function SettingsStep({ cfg, setCfg, conditions, setConditions, result, onNext }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [csvMsg, setCsvMsg] = useState<{ text: string; err?: boolean } | null>(null);
  const spec = SPEC[cfg.series];
  const f = result?.fields ?? {};
  const ioErr = result?.io ?? {};
  const update = (patch: Partial<Config>) => setCfg({ ...cfg, ...patch });
  const toggle = (key: "modules" | "modes") => (o: string, on: boolean) =>
    update({ [key]: on ? [...cfg[key], o] : cfg[key].filter((m) => m !== o) });
  const setRow = (i: number, patch: Partial<Config["io_list"][number]>) =>
    update({ io_list: cfg.io_list.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) });
  const bool = (b: boolean) => (b ? "true" : "false");

  const importCsv = async (file: File) => {
    if (file.size > 1_000_000) return setCsvMsg({ text: "파일이 너무 커요. (1MB 이하)", err: true });
    const { rows, warnings } = parseIoCsv(await file.text());
    if (!rows.length) return setCsvMsg({ text: "가져올 행이 없어요. 열 순서는 디바이스, 이름, 종류, 설명이에요.", err: true });
    const kept = cfg.io_list.filter((r) => r.device.trim() || r.name.trim());
    update({ io_list: [...kept, ...rows] });
    setCsvMsg({ text: `${rows.length}개 신호를 가져왔어요.${warnings.length ? " " + warnings.slice(0, 3).join(" ") : ""}` });
  };

  const loadTemplate = (p: { config: Partial<Config>; conditions: Condition[] }) => {
    const base = initialConfig();
    const c = { ...base, ...p.config, safety_ack: false } as Config;
    if (!c.io_list?.length) c.io_list = base.io_list;
    setCfg(c);
    setConditions(p.conditions.length ? p.conditions.map((x) => ({ text: x.text, must_pass: x.must_pass })) : [{ text: "", must_pass: true }]);
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); onNext(); }} noValidate>
      <TemplatesCard
        current={() => ({
          config: { ...cfg, safety_ack: false },
          conditions: conditions.filter((c) => c.text.trim()),
        })}
        onLoad={loadTemplate}
      />
      <Card title="PLC 사양" desc="사용할 MELSEC 시리즈와 CPU, 프로그램 언어를 선택해요.">
        <div className="grid">
          <Field label="MELSEC 시리즈" required error={f.series}>
            <select value={cfg.series} onChange={(e) => update({ series: e.target.value, cpu: "", language: "", software: "" })}>
              <option value="">선택하세요</option>
              {Object.keys(SPEC).map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="CPU 모델" required error={f.cpu}>
            <select value={cfg.cpu} disabled={!spec} onChange={(e) => update({ cpu: e.target.value })}>
              <option value="">{spec ? "선택하세요" : "시리즈를 먼저 선택"}</option>
              {spec && Object.keys(spec.cpus).map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="프로그램 언어" required error={f.language}>
            <select value={cfg.language} disabled={!spec} onChange={(e) => update({ language: e.target.value })}>
              <option value="">선택하세요</option>
              {spec?.languages.map((l) => <option key={l} value={l}>{LANGUAGE_LABELS[l]}</option>)}
            </select>
          </Field>
          <Field label="GX Works 버전" required error={f.software}>
            <select value={cfg.software} disabled={!spec} onChange={(e) => update({ software: e.target.value })}>
              <option value="">선택하세요</option>
              {spec?.software.map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="입력(X) 점수" required error={f.x_points} hint={cfg.cpu ? `최대 ${spec.cpus[cfg.cpu].max_x}점` : undefined}>
            <input type="number" min={0} value={cfg.x_points} onChange={(e) => update({ x_points: e.target.value })} />
          </Field>
          <Field label="출력(Y) 점수" required error={f.y_points} hint={cfg.cpu ? `최대 ${spec.cpus[cfg.cpu].max_y}점` : undefined}>
            <input type="number" min={0} value={cfg.y_points} onChange={(e) => update({ y_points: e.target.value })} />
          </Field>
        </div>
        {f.compat && <div className="banner err">{f.compat}</div>}
      </Card>

      <Card
        title="입출력 신호 목록"
        desc={spec ? `${spec.notation === "hex" ? "16진수" : "8진수"} 표기 · X는 입력, Y는 출력` : "시리즈를 선택하면 디바이스 표기 규칙이 표시돼요."}
      >
        <div className="io">
          {cfg.io_list.map((r, i) => (
            <div key={i} className={"io-row" + (ioErr[i] ? " has-error" : "")}>
              <input aria-label="디바이스" placeholder={spec?.notation === "octal" ? "X0 / Y10" : "X0 / Y1F"} value={r.device} onChange={(e) => setRow(i, { device: e.target.value })} />
              <input aria-label="이름" placeholder="START_PB" value={r.name} onChange={(e) => setRow(i, { name: e.target.value })} />
              <select aria-label="종류" value={r.kind} onChange={(e) => setRow(i, { kind: e.target.value })}>
                {IO_KINDS.map((k) => <option key={k}>{k}</option>)}
              </select>
              <input aria-label="설명" placeholder="설명 (선택)" value={r.desc} onChange={(e) => setRow(i, { desc: e.target.value })} />
              <button type="button" className="icon-btn" aria-label="행 삭제" onClick={() => update({ io_list: cfg.io_list.filter((_, idx) => idx !== i) })}>✕</button>
              {ioErr[i] && <span className="msg err io-msg">{ioErr[i]}</span>}
            </div>
          ))}
        </div>
        {f.io_empty && <div className="banner err">{f.io_empty}</div>}
        <div className="io-actions">
          <button type="button" className="btn ghost" onClick={() => update({ io_list: [...cfg.io_list, emptyRow()] })}>＋ 신호 추가</button>
          <button type="button" className="btn ghost" onClick={() => fileRef.current?.click()}>CSV 가져오기</button>
          <button type="button" className="btn ghost" onClick={downloadCsvTemplate}>CSV 양식 받기</button>
          <input
            ref={fileRef} type="file" accept=".csv,text/csv" hidden aria-label="CSV 파일 선택"
            onChange={(e) => { const f0 = e.target.files?.[0]; if (f0) importCsv(f0); e.target.value = ""; }}
          />
        </div>
        <p className="hint">엑셀은 "다른 이름으로 저장 → CSV UTF-8"로 저장한 뒤 가져오세요. 열 순서: 디바이스, 이름, 종류, 설명. 기존 입력에 이어 붙어요.</p>
        {csvMsg && <div className={"banner " + (csvMsg.err ? "err" : "ok")} role="status">{csvMsg.text}</div>}
      </Card>

      <Card title="제어 정보" desc="제어 대상과 안전 입력을 알려 주세요.">
        <div className="grid">
          <Field label="제어 대상 유형" required error={f.control_target}>
            <select value={cfg.control_target} onChange={(e) => update({ control_target: e.target.value })}>
              <option value="">선택하세요</option>
              {CONTROL_TARGETS.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field group label="비상정지 / 안전 입력" error={f.emergency_stop}>
            <Segmented
              value={bool(cfg.emergency_stop.used) as "true" | "false"}
              options={[["false", "미사용"], ["true", "사용"]]}
              onChange={(v) => update({ emergency_stop: { ...cfg.emergency_stop, used: v === "true" } })}
            />
            {cfg.emergency_stop.used && (
              <input className="mt" placeholder="비상정지 디바이스 (예: X0)" value={cfg.emergency_stop.device}
                onChange={(e) => update({ emergency_stop: { ...cfg.emergency_stop, device: e.target.value } })} />
            )}
          </Field>
        </div>
        <label className={"ack" + (f.safety_ack ? " has-error" : "")}>
          <input type="checkbox" checked={cfg.safety_ack} onChange={(e) => update({ safety_ack: e.target.checked })} />
          <span><b>안전 고지 동의 (필수)</b><br />{SAFETY_NOTICE}</span>
        </label>
        {f.safety_ack && <span className="msg err">{f.safety_ack}</span>}
      </Card>

      <Card title="선택 항목" desc="입력하지 않으면 기본값이 적용되고, 가정사항에 기록돼요.">
        <div className="grid">
          <Field group label="사용 모듈"><Chips options={MODULES} selected={cfg.modules} onToggle={toggle("modules")} /></Field>
          <Field group label="운전 모드"><Chips options={OPERATION_MODES} selected={cfg.modes} onToggle={toggle("modes")} /></Field>
          <Field label="M 시작 번호"><input type="number" min={0} value={cfg.device_rule.M} onChange={(e) => update({ device_rule: { ...cfg.device_rule, M: Number(e.target.value) } })} /></Field>
          <Field label="D 시작 번호"><input type="number" min={0} value={cfg.device_rule.D} onChange={(e) => update({ device_rule: { ...cfg.device_rule, D: Number(e.target.value) } })} /></Field>
          <Field group label="타이머 시간 단위">
            <Segmented value={String(cfg.timer_unit_ms) as "100" | "10" | "1"} options={[["100", "100ms"], ["10", "10ms"], ["1", "1ms"]]} onChange={(v) => update({ timer_unit_ms: Number(v) })} />
          </Field>
          <Field group label="정전 시 상태">
            <Segmented value={bool(cfg.retentive) as "true" | "false"} options={[["false", "비유지"], ["true", "유지(래치)"]]} onChange={(v) => update({ retentive: v === "true" })} />
          </Field>
          <Field group label="알람/에러 처리">
            <Segmented value={bool(cfg.alarm) as "true" | "false"} options={[["false", "미사용"], ["true", "램프·부저 사용"]]} onChange={(v) => update({ alarm: v === "true" })} />
          </Field>
          <Field group label="주석 언어">
            <Segmented value={cfg.comment_lang as "ko" | "en" | "ja"} options={[["ko", "한국어"], ["en", "English"], ["ja", "日本語"]]} onChange={(v) => update({ comment_lang: v })} />
          </Field>
          <Field label="프로젝트 이름" error={f.project_name} hint="영문·숫자·_ 최대 32자 (비우면 자동 생성)">
            <input maxLength={32} value={cfg.project_name} onChange={(e) => update({ project_name: e.target.value })} />
          </Field>
          <Field label="비고 / 기타 제약"><input value={cfg.note} onChange={(e) => update({ note: e.target.value })} /></Field>
        </div>
      </Card>

      <div className="actions">
        <span />
        <button type="submit" className="btn primary">다음: 동작 조건 입력 →</button>
      </div>
    </form>
  );
}

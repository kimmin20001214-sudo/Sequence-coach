import { useState } from "react";
import {
  initialConfig, SAFETY_NOTICE, type Condition, type Config,
} from "./spec";
import { validateConfig, hasErrors, type ValidationResult } from "./validate";
import SettingsStep from "./SettingsStep";
import ConditionsStep from "./ConditionsStep";
import { Card } from "./ui";
import "./App.css";

const STEPS = ["기본 설정", "동작 조건", "완료"];

export default function App() {
  const [step, setStep] = useState(0);
  const [cfg, setCfg] = useState<Config>(initialConfig);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [conditions, setConditions] = useState<Condition[]>([{ text: "", must_pass: true }]);
  const [condError, setCondError] = useState("");
  const [saved, setSaved] = useState<object | null>(null);

  const go = (n: number) => {
    setStep(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const next = () => {
    const r = validateConfig(cfg);
    setResult(r);
    if (hasErrors(r)) window.scrollTo({ top: 0, behavior: "smooth" });
    else go(1);
  };

  const save = () => {
    const list = conditions.filter((c) => c.text.trim());
    if (!list.length) return setCondError("동작 조건을 1개 이상 입력해 주세요.");
    if (!list.some((c) => c.must_pass)) return setCondError("필수 조건을 1개 이상 지정해 주세요.");
    setCondError("");
    const out = {
      plc_config: {
        series: cfg.series, cpu: cfg.cpu, language: cfg.language, software: cfg.software,
        x_points: Number(cfg.x_points), y_points: Number(cfg.y_points), control_target: cfg.control_target,
        emergency_stop: cfg.emergency_stop, modules: cfg.modules, device_rule: cfg.device_rule,
        timer_unit_ms: cfg.timer_unit_ms, modes: cfg.modes, retentive: cfg.retentive, alarm: cfg.alarm,
        project_name: cfg.project_name || "PRJ_" + Date.now().toString(36).toUpperCase(),
        comment_lang: cfg.comment_lang, note: cfg.note,
      },
      io_list: cfg.io_list.map((r) => ({ ...r, device: r.device.trim().toUpperCase(), name: r.name.trim() })),
      conditions: list.map((c, i) => ({ id: "C" + (i + 1), text: c.text.trim(), must_pass: c.must_pass })),
    };
    localStorage.setItem("melsec_project", JSON.stringify(out));
    setSaved(out);
    go(2);
  };

  const errCount = result ? Object.keys(result.fields).length + Object.keys(result.io).length : 0;

  return (
    <div className="shell">
      <div className="notice" role="note">⚠ {SAFETY_NOTICE}</div>
      <header className="top">
        <div className="brand">
          <span className="logo">⚡</span>
          <div>
            <h1>MELSEC PLC 회로 설계 지원</h1>
            <p>조건을 입력하면 에이전트가 분석·설계·검증해요</p>
          </div>
        </div>
      </header>
      <div className="layout">
        <nav className="stepper" aria-label="진행 단계">
          {STEPS.map((s, i) => (
            <div key={s} className={"step" + (i === step ? " active" : i < step ? " done" : "")} aria-current={i === step ? "step" : undefined}>
              <span className="dot">{i < step ? "✓" : i + 1}</span>
              <span>{s}</span>
            </div>
          ))}
        </nav>
        <main>
          {step === 0 && errCount > 0 && (
            <div className="banner err" role="alert">입력을 확인해 주세요. 오류 {errCount}건이 있어요.</div>
          )}
          {step === 0 && (
            <SettingsStep
              cfg={cfg}
              setCfg={(c) => { setCfg(c); if (result) setResult(validateConfig(c)); }}
              result={result}
              onNext={next}
            />
          )}
          {step === 1 && <ConditionsStep conditions={conditions} setConditions={setConditions} error={condError} onBack={() => go(0)} onSave={save} />}
          {step === 2 && (
            <>
              <Card title="저장 완료" desc="백엔드 연동 전이라 브라우저에 임시 저장했어요. 다음 단계에서 에이전트가 이 정보를 사용해요.">
                <pre className="json">{JSON.stringify(saved, null, 2)}</pre>
              </Card>
              <div className="actions"><button type="button" className="btn ghost" onClick={() => go(1)}>← 조건 수정</button><span /></div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

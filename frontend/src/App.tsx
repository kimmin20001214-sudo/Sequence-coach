import { useEffect, useState } from "react";
import {
  initialConfig, applyMeta, SAFETY_NOTICE, type Condition, type Config,
} from "./spec";
import { fetchMeta, saveProject, ApiError, type SavedProject } from "./api";
import { validateConfig, hasErrors, type ValidationResult } from "./validate";
import SettingsStep from "./SettingsStep";
import ConditionsStep from "./ConditionsStep";
import { Card } from "./ui";
import "./App.css";

const STEPS = ["기본 설정", "동작 조건", "완료"];

export default function App() {
  const [metaState, setMetaState] = useState<"loading" | "ready" | string>("loading");
  const load = () =>
    fetchMeta()
      .then((m) => { applyMeta(m); setMetaState("ready"); })
      .catch((e: Error) => setMetaState(e.message));
  const retry = () => { setMetaState("loading"); load(); };
  useEffect(() => { load(); }, []);

  if (metaState === "loading") return <div className="shell"><p className="boot">기준 데이터를 불러오는 중…</p></div>;
  if (metaState !== "ready")
    return (
      <div className="shell">
        <div className="banner err" role="alert">
          {metaState}
          <div><button type="button" className="btn ghost" onClick={retry}>다시 시도</button></div>
        </div>
      </div>
    );
  return <Wizard />;
}

function Wizard() {
  const [step, setStep] = useState(0);
  const [cfg, setCfg] = useState<Config>(initialConfig);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [conditions, setConditions] = useState<Condition[]>([{ text: "", must_pass: true }]);
  const [condError, setCondError] = useState("");
  const [saved, setSaved] = useState<SavedProject | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

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

  const save = async () => {
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
        project_name: cfg.project_name, safety_ack: cfg.safety_ack,
        comment_lang: cfg.comment_lang, note: cfg.note,
      },
      io_list: cfg.io_list.map((r) => ({ ...r, device: r.device.trim().toUpperCase(), name: r.name.trim() })),
      conditions: list.map((c, i) => ({ id: "C" + (i + 1), text: c.text.trim(), must_pass: c.must_pass })),
    };
    setSaving(true);
    setSaveError("");
    try {
      setSaved(await saveProject(out));
      go(2);
    } catch (e) {
      const err = e as ApiError;
      if (err.validation) {
        setResult(err.validation);
        go(0);
      } else {
        setSaveError(err.message);
      }
    } finally {
      setSaving(false);
    }
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
          {step === 1 && <ConditionsStep conditions={conditions} setConditions={setConditions} error={condError || saveError} saving={saving} onBack={() => go(0)} onSave={save} />}
          {step === 2 && (
            <>
              <Card title="저장 완료" desc={`서버에 저장했어요. (프로젝트 ID: ${saved?.id}) 다음 단계에서 에이전트가 이 정보를 사용해요.`}>
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

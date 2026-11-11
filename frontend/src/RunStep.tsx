import { useEffect, useRef, useState } from "react";
import { fetchAgentMode, fetchStatus, runProject, ApiError, type JobStatus } from "./api";
import { Card } from "./ui";
import { Conditions, Design, Fixes, Simulation, Stepper, Summary, type DesignData, type VerificationData } from "./Result";
import { CriteriaButton } from "./Criteria";

const STEPS = [
  { key: "analyze", label: "조건 분석" },
  { key: "design", label: "회로 설계" },
  { key: "verify", label: "검증" },
  { key: "done", label: "완료" },
];
const STEP_INDEX: Record<string, number> = {
  INPUT_VALIDATED: 0, ANALYZING: 0, NEEDS_INPUT: 0,
  DESIGNING: 1,
  VERIFYING: 2, FIXING: 2,
  COMPLETED: 4, GENERATING: 4, DELIVERED: 4,
  ESCALATED: 2,
};

const STATE_LABEL: Record<string, string> = {
  INPUT_VALIDATED: "입력 확인됨",
  ANALYZING: "조건 분석 중",
  NEEDS_INPUT: "추가 정보 필요",
  DESIGNING: "설계 에이전트 작업 중 · 완료되면 회로가 아래에 표시돼요",
  VERIFYING: "검증 중",
  FIXING: "자동 수정 중 · 수정 에이전트 작업 중",
  COMPLETED: "검증 통과",
  GENERATING: "파일 생성 중",
  DELIVERED: "전달 완료",
  ESCALATED: "자동 수정 실패 또는 검증 실패 · 사람 확인 필요",
  FAILED: "실패",
};
const FINAL = new Set(["NEEDS_INPUT", "COMPLETED", "DELIVERED", "ESCALATED", "FAILED"]);

const TYPICAL: Record<string, string> = {
  ANALYZING: "조건 분석은 보통 1분 안팎",
  DESIGNING: "회로 설계는 보통 30초~1분",
  VERIFYING: "검증은 몇 초",
  FIXING: "자동 수정은 보통 1~2분",
};

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function Elapsed({ events, state }: { events: JobStatus["events"]; state: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const at = (i: number) => Date.parse(events[i]?.created_at ?? "");
  const total = Math.max(0, Math.round((now - at(0)) / 1000));
  const step = Math.max(0, Math.round((now - at(events.length - 1)) / 1000));
  if (!events.length || Number.isNaN(total)) return null;
  return (
    <p className="elapsed" role="status">
      ⏱ 전체 {mmss(total)} · 이 단계 {mmss(step)}째 — AI가 생각하는 시간이라 기다려야 해요. {TYPICAL[state] ?? ""}
    </p>
  );
}

export default function RunStep({ projectId, page, onPage }: { projectId: string; page: number; onPage: (n: number) => void }) {
  const [mode, setMode] = useState<string | null | undefined>(undefined);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const timer = useRef<number | undefined>(undefined);

  const poll = (id: string) => {
    fetchStatus(id)
      .then((s) => {
        setStatus(s.job_id ? s : null);
        if (s.job_id && !FINAL.has(s.state)) {
          setRunning(true);
          timer.current = window.setTimeout(() => poll(id), 2000);
        } else {
          setRunning(false);
        }
      })
      .catch((e: Error) => { setError(e.message); setRunning(false); });
  };

  useEffect(() => {
    fetchAgentMode().then(setMode).catch(() => setMode(null));
    poll(projectId);
    return () => window.clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const start = async (withAnswers = false) => {
    setError("");
    const list = withAnswers
      ? (status?.questions ?? []).map((q) => ({ question: q, answer: (answers[q] ?? "").trim() }))
      : [];
    if (list.some((a) => !a.answer)) return setError("모든 질문에 답해 주세요.");
    setRunning(true);
    try {
      setStatus(await runProject(projectId, list));
      setAnswers({});
      poll(projectId);
    } catch (e) {
      setError((e as ApiError).message);
      setRunning(false);
    }
  };

  const failReason = status?.state === "FAILED"
    ? String([...status.events].reverse().find((e) => e.kind === "error")?.data.reason ?? "")
    : "";
  const agentNotes = status?.events.filter((e) => e.kind === "agent_message") ?? [];
  const design = [...(status?.events ?? [])].reverse().find((e) => e.kind === "design")?.data as DesignData | undefined;
  const fixes = (status?.events ?? []).filter((e) => e.kind === "fix_applied" || e.kind === "fix_rejected");

  const verification = [...(status?.events ?? [])].reverse().find((e) => e.kind === "verification")?.data as VerificationData | undefined;
  const escalateReason = status?.state === "ESCALATED"
    ? String([...status.events].reverse().find((e) => e.kind === "escalated")?.data.reason ?? "")
    : "";

  const nav = (back: [string, number] | null, fwd: [string, number] | null) => (
    <div className="actions">
      {back ? <button type="button" className="btn ghost" onClick={() => onPage(back[1])}>{back[0]}</button> : <span />}
      {fwd ? <button type="button" className="btn primary" onClick={() => onPage(fwd[1])}>{fwd[0]}</button> : <span />}
    </div>
  );

  if (page === 3) {
    return (
      <Card title="검증 결과" desc="서버가 회로를 모의 실행해서 조건을 하나씩 확인한 결과예요.">
        {status && verification ? (
          <>
            <Summary v={verification} fixCount={fixes.length} state={status.state} />
            <CriteriaButton />
            {escalateReason && <div className="banner err" role="alert">{escalateReason}</div>}
            <Conditions v={verification} />
            {fixes.length > 0 && <Fixes events={fixes} />}
            {design && <Design d={design} />}
          </>
        ) : (
          <p className="notice">아직 검증 결과가 없어요. 먼저 이전 단계에서 분석을 실행해 주세요.</p>
        )}
        {nav(["← 분석 단계로", 2], design?.ir ? ["모의 실행 →", 4] : null)}
      </Card>
    );
  }

  if (page === 4) {
    return (
      <Card title="모의 실행" desc="설계된 회로를 직접 눌러 보며 동작을 확인해요.">
        {design ? <Simulation d={design} v={verification} /> : <p className="notice">아직 설계 결과가 없어요. 먼저 분석을 실행해 주세요.</p>}
        {nav(["← 검증 결과", 3], null)}
      </Card>
    );
  }

  return (
    <Card title="에이전트에게 설계 요청" desc="AI 에이전트가 조건을 분석해요. 새로고침해도 마지막 분석 결과를 다시 볼 수 있어요.">
      {mode === null && (
        <div className="banner err" role="status">에이전트가 아직 연결되지 않았어요. Copilot Studio 연결 후 실행할 수 있어요.</div>
      )}
      {mode === "demo" && (
        <div className="banner err" role="status">시연 모드예요. 실제 AI 분석이 아니라 화면 흐름만 확인해요.</div>
      )}
      <button type="button" className="btn primary" disabled={!mode || running} onClick={() => start()}>
        {running ? "분석 중…" : status ? "다시 실행" : "분석 시작"}
      </button>
      {error && <div className="banner err" role="alert">{error}</div>}
      {status && (
        <div aria-live="polite">
          {status.state !== "FAILED" && (
            <Stepper steps={STEPS} current={STEP_INDEX[status.state] ?? 0} failed={status.state === "ESCALATED" || status.state === "NEEDS_INPUT"} />
          )}
          <h3 className="state-line">{STATE_LABEL[status.state] ?? status.state}</h3>
          {running && !FINAL.has(status.state) && <Elapsed events={status.events} state={status.state} />}
          {failReason && <div className="banner err" role="alert">{failReason}</div>}
          {status.state === "NEEDS_INPUT" && (
            <>
              <p>아래 질문에 답하면 그 내용을 반영해 다시 분석해요.</p>
              {status.questions.map((q) => (
                <label key={q} className="field">
                  <span className="field-label">{q}</span>
                  <input value={answers[q] ?? ""} onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })} maxLength={500} />
                </label>
              ))}
              <button type="button" className="btn primary" disabled={running} onClick={() => start(true)}>답변 반영해 다시 분석</button>
            </>
          )}
          {agentNotes.map((e) => <p key={e.created_at + String(e.data.text)}>💬 {String(e.data.text)}</p>)}
          {escalateReason && <div className="banner err" role="alert">{escalateReason}</div>}
        </div>
      )}
      {nav(null, verification && !running ? ["검증 결과 보기 →", 3] : null)}
    </Card>
  );
}
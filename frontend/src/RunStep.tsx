import { useEffect, useRef, useState } from "react";
import { fetchAgentMode, fetchStatus, runProject, ApiError, type JobStatus } from "./api";
import { Card } from "./ui";

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
const FINAL = new Set(["NEEDS_INPUT", "DESIGNING", "COMPLETED", "DELIVERED", "ESCALATED", "FAILED"]);
const SHOWN = new Set(["created", "started", "requirements", "questions", "error", "verified", "escalated"]);

interface DesignData {
  il: string[];
  io_used: { device: string; name: string; kind: string; desc: string }[];
  explanation: { rung_id: string; condition_ids: string[]; text: string }[];
  assumptions: string[];
  limitations: string[];
}

interface VerificationData {
  passed: boolean;
  conditions: { id: string; text: string; must_pass: boolean; status: "PASS" | "FAIL" | "UNVERIFIED"; message: string; rung_id: string; notes: string[] }[];
  problems: { message: string; rung_id: string }[];
  notice: string;
}

const RESULT_LABEL = { PASS: "✅ 통과", FAIL: "❌ 실패", UNVERIFIED: "⚠️ 검증 못 함" };

function VerificationView({ v }: { v: VerificationData }) {
  return (
    <div>
      <h3>검증 결과</h3>
      <table>
        <thead><tr><th>조건</th><th>내용</th><th>결과</th><th>설명</th></tr></thead>
        <tbody>
          {v.conditions.map((c) => (
            <tr key={c.id}>
              <td>{c.id}</td>
              <td>{c.text}</td>
              <td>{RESULT_LABEL[c.status]}</td>
              <td>{c.message}{c.rung_id && ` (렁 ${c.rung_id})`}{c.notes.map((n) => <div key={n}><small>{n}</small></div>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {v.problems.length > 0 && <ul>{v.problems.map((p) => <li key={p.message}>{p.message}</li>)}</ul>}
      <div className="banner err" role="note">{v.notice}</div>
    </div>
  );
}

function FixHistory({ events }: { events: JobStatus["events"] }) {
  return (
    <div>
      <h3>자동 수정 기록</h3>
      <ol>
        {events.map((e, i) => {
          const diff = e.data.diff as { added: string[]; removed: string[]; changed: { rung_id: string; summary: string }[] } | undefined;
          return (
            <li key={i}>
              {e.kind === "fix_applied" ? "✅ 수정 성공" : "❌ 수정 거부"}: {String(e.data.reason)}
              {e.kind === "fix_applied" && e.data.agent_reason ? <div><small>수정 이유: {String(e.data.agent_reason)}</small></div> : null}
              {diff && (
                <ul>
                  {diff.changed.map((c) => <li key={c.rung_id}>렁 {c.rung_id}: {c.summary}</li>)}
                  {diff.added.map((r) => <li key={"a" + r}>렁 {r} 추가</li>)}
                  {diff.removed.map((r) => <li key={"r" + r}>렁 {r} 삭제</li>)}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      <div className="banner err" role="note">수정이 성공했는지는 AI가 아니라 서버가 모든 조건을 다시 모의 실행해서 확인해요.</div>
    </div>
  );
}

function DesignView({ d }: { d: DesignData }) {
  return (
    <div>
      <h3>설계 결과</h3>
      <div className="banner err" role="note">자동 생성된 초안이에요. 실제 장비에 넣기 전에 반드시 사람이 확인하세요.</div>
      <h4>명령어(IL)</h4>
      <pre>{d.il.join("\n")}</pre>
      <h4>사용한 입출력</h4>
      <ul>{d.io_used.map((r) => <li key={r.device}>{r.device} · {r.name} {r.desc && `(${r.desc})`}</li>)}</ul>
      <h4>회로 설명</h4>
      <ul>{d.explanation.map((x) => <li key={x.rung_id}>{x.text} <small>({x.condition_ids.join(", ")})</small></li>)}</ul>
      {d.assumptions.length > 0 && <><h4>가정</h4><ul>{d.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></>}
      {d.limitations.length > 0 && <><h4>제한 사항</h4><ul>{d.limitations.map((a) => <li key={a}>{a}</li>)}</ul></>}
    </div>
  );
}

export default function RunStep({ projectId }: { projectId: string }) {
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
          <h3>상태: {STATE_LABEL[status.state] ?? status.state}</h3>
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
          {fixes.length > 0 && <FixHistory events={fixes} />}
          {verification && <VerificationView v={verification} />}
          {design && <DesignView d={design} />}
          <ol>
            {status.events.filter((e) => SHOWN.has(e.kind)).map((e, i) => (
              <li key={i}>{STATE_LABEL[e.state] ?? e.state}</li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}

import { useEffect, useRef, useState } from "react";
import { fetchAgentMode, fetchStatus, runProject, ApiError, type JobStatus } from "./api";
import { Card } from "./ui";

const STATE_LABEL: Record<string, string> = {
  INPUT_VALIDATED: "입력 확인됨",
  ANALYZING: "조건 분석 중",
  NEEDS_INPUT: "추가 정보 필요",
  DESIGNING: "분석 완료 · 설계 단계 (설계 에이전트 연결 전)",
  VERIFYING: "검증 중",
  FIXING: "수정 중",
  COMPLETED: "검증 통과",
  GENERATING: "파일 생성 중",
  DELIVERED: "전달 완료",
  ESCALATED: "자동 수정 한도 초과 · 사람 확인 필요",
  FAILED: "실패",
};
const FINAL = new Set(["NEEDS_INPUT", "DESIGNING", "COMPLETED", "DELIVERED", "ESCALATED", "FAILED"]);

export default function RunStep({ projectId }: { projectId: string }) {
  const [mode, setMode] = useState<string | null | undefined>(undefined);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    fetchAgentMode().then(setMode).catch(() => setMode(null));
    return () => window.clearTimeout(timer.current);
  }, []);

  const poll = (id: string) => {
    fetchStatus(id)
      .then((s) => {
        setStatus(s);
        if (FINAL.has(s.state)) setRunning(false);
        else timer.current = window.setTimeout(() => poll(id), 2000);
      })
      .catch((e: Error) => { setError(e.message); setRunning(false); });
  };

  const start = async () => {
    setError("");
    setRunning(true);
    try {
      setStatus(await runProject(projectId));
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

  return (
    <Card title="에이전트에게 설계 요청" desc="AI 에이전트가 조건을 분석해요. 분석 결과는 아래에서 바로 확인할 수 있어요.">
      {mode === null && (
        <div className="banner err" role="status">에이전트가 아직 연결되지 않았어요. Copilot Studio 연결 후 실행할 수 있어요.</div>
      )}
      {mode === "demo" && (
        <div className="banner err" role="status">시연 모드예요. 실제 AI 분석이 아니라 화면 흐름만 확인해요.</div>
      )}
      <button type="button" className="btn primary" disabled={!mode || running} onClick={start}>
        {running ? "분석 중…" : status ? "다시 실행" : "분석 시작"}
      </button>
      {error && <div className="banner err" role="alert">{error}</div>}
      {status && (
        <div aria-live="polite">
          <h3>상태: {STATE_LABEL[status.state] ?? status.state}</h3>
          {failReason && <div className="banner err" role="alert">{failReason}</div>}
          {status.state === "NEEDS_INPUT" && (
            <>
              <p>아래 질문에 맞게 조건이나 I/O 목록을 고친 뒤 다시 실행해 주세요.</p>
              <ul>{status.questions.map((q) => <li key={q}>{q}</li>)}</ul>
            </>
          )}
          {agentNotes.map((e) => <p key={e.created_at + String(e.data.text)}>💬 {String(e.data.text)}</p>)}
          <ol>
            {status.events.filter((e) => e.kind !== "agent_message").map((e, i) => (
              <li key={i}>{STATE_LABEL[e.state] ?? e.state}</li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}

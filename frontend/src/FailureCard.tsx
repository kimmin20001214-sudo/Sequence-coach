import { useState } from "react";

type Info = { stage: string; title: string; what: string; todo: string[] };

const GENERIC: Info = {
  stage: "알 수 없음",
  title: "작업을 끝내지 못했어요",
  what: "자세한 원인을 분류하지 못했어요. 아래 원문 사유를 확인해 주세요.",
  todo: ["조건을 확인하고 다시 실행해 보세요.", "계속 실패하면 팀장에게 원문 사유를 알려 주세요."],
};

// 서버가 이벤트에 남기는 실패 종류(code)별 안내 문구
const INFO: Record<string, Info> = {
  AGENT_CALL_FAILED: {
    stage: "에이전트 호출",
    title: "에이전트와 연결하지 못했어요",
    what: "AI 에이전트(Copilot Studio)를 부르는 중 오류가 났어요. 입력한 조건 때문이 아닐 수 있어요.",
    todo: ["잠시 뒤 '다시 실행'을 눌러 보세요.", "계속 실패하면 팀장에게 알려 연결 설정을 확인하게 해 주세요."],
  },
  AGENT_TIMEOUT: {
    stage: "에이전트 응답 대기",
    title: "에이전트가 시간 안에 답하지 못했어요",
    what: "정해진 시간(기본 180초) 안에 에이전트가 결과를 보내지 않아 실패로 처리했어요.",
    todo: ["'다시 실행'을 눌러 보세요.", "조건이 너무 길거나 복잡하면 나누어 입력해 보세요."],
  },
  DESIGN_REJECTED: {
    stage: "회로 설계",
    title: "설계한 회로가 규칙 검사를 통과하지 못했어요",
    what: "설계 에이전트가 만든 회로가 서버의 규칙 검사에서 여러 번 거부됐어요.",
    todo: ["조건 설명에 입력·출력·정지 동작을 더 구체적으로 적고 다시 실행해 보세요.", "비상정지가 있으면 '모든 출력 OFF' 동작도 적어 주세요."],
  },
  FIX_LIMIT: {
    stage: "자동 수정",
    title: "자동 수정으로 해결하지 못했어요",
    what: "수정 에이전트가 정해진 횟수만큼 고쳤지만 검증을 통과하지 못했어요. 이 회로는 완성된 것이 아니에요.",
    todo: ["검증 결과에서 실패한 조건을 확인하세요.", "조건을 더 분명하게 고쳐 다시 실행하거나 전문가가 직접 확인해 주세요."],
  },
  FIX_NO_RESPONSE: {
    stage: "자동 수정",
    title: "수정 에이전트가 응답하지 못했어요",
    what: "검증에 실패해 수정을 요청했지만 수정 에이전트가 답하지 않았어요.",
    todo: ["검증 결과에서 실패한 조건을 확인하세요.", "'다시 실행'을 눌러 보거나 전문가가 직접 확인해 주세요."],
  },
  FIX_DISABLED: {
    stage: "검증",
    title: "검증에 실패했고 자동 수정은 꺼져 있어요",
    what: "회로가 일부 조건을 통과하지 못했어요. 이 서버에서는 자동 수정을 사용하지 않아요.",
    todo: ["검증 결과에서 실패한 조건을 확인하세요.", "조건을 고쳐 다시 실행하거나 전문가가 직접 확인해 주세요."],
  },
  VERIFY_ERROR: {
    stage: "검증",
    title: "검증 중 서버 오류가 났어요",
    what: "회로를 검증하는 중 서버에서 예상하지 못한 오류가 났어요. 회로가 맞는지 틀린지 판단하지 못했어요.",
    todo: ["'다시 실행'을 눌러 보세요.", "계속 실패하면 팀장에게 원문 사유를 알려 주세요."],
  },
};

function failureInfo(code: string | undefined): Info {
  return (code && INFO[code]) || GENERIC;
}

export function FailureCard({ state, code, reason }: { state: "FAILED" | "ESCALATED"; code?: string; reason: string }) {
  const info = failureInfo(code);
  const [popup, setPopup] = useState(true);
  return (
    <>
      {popup && (
        <div className="modal-back" onClick={() => setPopup(false)}>
          <div className="modal failure-modal" role="alertdialog" aria-modal="true" aria-label={info.title} onClick={(e) => e.stopPropagation()}>
            <h3><svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5L22.5 21h-21L12 2.5z" fill="#facc15" stroke="#facc15" strokeWidth="2" strokeLinejoin="round" /><path d="M12 9.5v5" stroke="#111" strokeWidth="2.2" strokeLinecap="round" /><circle cx="12" cy="17.6" r="1.3" fill="#111" /></svg>{info.title}</h3>
            <p><strong className="warn-line">{state === "FAILED" ? "작업이 실패했어요" : "사람이 확인해 주세요"}</strong><br />{info.what}</p>
            <button onClick={() => setPopup(false)}>확인</button>
          </div>
        </div>
      )}
      <FailureInline state={state} code={code} reason={reason} info={info} />
    </>
  );
}

function FailureInline({ state, code, reason, info }: { state: "FAILED" | "ESCALATED"; code?: string; reason: string; info: Info }) {
  return (
    <div className="failure-card" role="alert">
      <h4>⚠ {info.title}</h4>
      <p className="failure-meta">
        단계: {info.stage} · 상태: {state === "FAILED" ? "실패" : "사람 확인 필요"}
      </p>
      <p>{info.what}</p>
      <p className="failure-todo-title">이렇게 해 보세요</p>
      <ul>{info.todo.map((t) => <li key={t}>{t}</li>)}</ul>
      {(reason || code) && (
        <details>
          <summary>자세히 보기</summary>
          {code && <p>오류 코드: {code}</p>}
          {reason && <p>원문 사유: {reason}</p>}
        </details>
      )}
    </div>
  );
}

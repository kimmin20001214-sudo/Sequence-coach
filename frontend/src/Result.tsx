import { lazy, Suspense, useState } from "react";
import type { JobStatus } from "./api";
import { GxGuide } from "./GxGuide";
import type { Ir } from "./sim/engine";

const PlcSimulator = lazy(() => import("./sim/PlcSimulator"));

export interface DesignData {
  ir?: Ir;
  il: string[];
  io_used: { device: string; name: string; kind: string; desc: string }[];
  explanation: { rung_id: string; condition_ids: string[]; text: string }[];
  assumptions: string[];
  limitations: string[];
}

export interface VerificationData {
  passed: boolean;
  conditions: { id: string; text: string; must_pass: boolean; status: "PASS" | "FAIL" | "UNVERIFIED"; message: string; rung_id: string; notes: string[] }[];
  problems: { message: string; rung_id: string }[];
  notice: string;
}

interface Diff { added: string[]; removed: string[]; changed: { rung_id: string; summary: string }[] }

const STATUS = {
  PASS: { icon: "✓", label: "통과", cls: "ok" },
  FAIL: { icon: "✕", label: "실패", cls: "bad" },
  UNVERIFIED: { icon: "!", label: "검증 못 함", cls: "warn" },
} as const;

export function Stepper({ steps, current, failed, times }: { steps: { key: string; label: string }[]; current: number; failed: boolean; times?: string[] }) {
  return (
    <ol className="run-stepper" aria-label="진행 단계">
      {steps.map((s, i) => (
        <li key={s.key} className={i < current ? "done" : i === current ? (failed ? "fail" : "now") : ""} aria-current={i === current ? "step" : undefined}>
          <span className="dot">{i < current ? <span className="chk">✓</span> : failed && i === current ? "✕" : i + 1}</span>
          <span className="lbl">{s.label}</span>
          {times?.[i] && <span className="lbl-time">{times[i]}</span>}
        </li>
      ))}
    </ol>
  );
}

export function Summary({ v, fixCount, state }: { v: VerificationData; fixCount: number; state: string }) {
  const total = v.conditions.length;
  const pass = v.conditions.filter((c) => c.status === "PASS").length;
  const unverified = v.conditions.filter((c) => c.status === "UNVERIFIED").length;
  const escalated = state === "ESCALATED";
  const ok = v.passed && !escalated;
  return (
    <div className={`summary ${ok ? "ok" : "bad"}`} role="status">
      <div className="summary-main">
        <span className="summary-icon">{ok ? "✓" : "!"}</span>
        <div>
          <strong>{ok ? "모든 조건이 검증을 통과했어요" : escalated ? "자동 수정에 실패했어요 · 사람이 확인해 주세요" : "검증을 통과하지 못한 조건이 있어요"}</strong>
          <div className="summary-sub">서버가 회로를 모의 실행해서 조건을 하나씩 확인한 결과예요.</div>
        </div>
      </div>
      <div className="stats">
        <div><b>{pass}/{total}</b><span>통과한 조건</span></div>
        {unverified > 0 && <div><b>{unverified}</b><span>검증 못 한 조건</span></div>}
        <div><b>{fixCount}</b><span>자동 수정 시도</span></div>
      </div>
    </div>
  );
}

export function Conditions({ v }: { v: VerificationData }) {
  return (
    <section className="block">
      <h3>조건별 검증 결과</h3>
      <ul className="cond-list">
        {v.conditions.map((c) => {
          const s = STATUS[c.status];
          const low = c.notes.find((n) => n.includes("신뢰도"));
          return (
            <li key={c.id} className={`cond ${s.cls}`}>
              <span className="cond-id">{c.id}</span>
              <div className="cond-body">
                <div className="cond-text">{c.text}</div>
                {c.message && <div className="cond-msg">{c.message}{c.rung_id && ` · 렁 ${c.rung_id}`}</div>}
                {c.notes.filter((n) => n !== low).map((n) => <div key={n} className="cond-note">{n}</div>)}
              </div>
              {low && <span className="pill low" tabIndex={0} data-tip={low}>검증 신뢰도 낮음</span>}
              <span className={`pill ${s.cls}`}><i aria-hidden>{s.icon}</i>{s.label}</span>
            </li>
          );
        })}
      </ul>
      {v.problems.length > 0 && (
        <ul className="problems">{v.problems.map((p) => <li key={p.message}>{p.message}</li>)}</ul>
      )}
      <p className="notice">{v.notice}</p>
    </section>
  );
}

export function Fixes({ events }: { events: JobStatus["events"] }) {
  return (
    <section className="block">
      <h3>자동 수정 기록</h3>
      <ul className="fix-list">
        {events.map((e, i) => {
          const diff = e.data.diff as Diff | undefined;
          const ok = e.kind === "fix_applied";
          return (
            <li key={i} className={ok ? "ok" : "bad"}>
              <div className="fix-head"><span className={`pill ${ok ? "ok" : "bad"}`}>{ok ? "수정 성공" : "수정 거부"}</span> {String(e.data.reason)}</div>
              {ok && e.data.agent_reason ? <div className="cond-msg">수정 이유: {String(e.data.agent_reason)}</div> : null}
              {diff && (
                <ul className="diff">
                  {diff.changed.map((c) => <li key={c.rung_id}>렁 {c.rung_id}: {c.summary}</li>)}
                  {diff.added.map((r) => <li key={"a" + r}>렁 {r} 추가</li>)}
                  {diff.removed.map((r) => <li key={"r" + r}>렁 {r} 삭제</li>)}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      <p className="notice">수정이 성공했는지는 AI가 아니라 서버가 모든 조건을 다시 모의 실행해서 확인해요.</p>
    </section>
  );
}

function Fold({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <details className="fold">
      <summary>{title}{count !== undefined && <span className="count">{count}</span>}</summary>
      <div className="fold-body">{children}</div>
    </details>
  );
}

export function Simulation({ d, v }: { d: DesignData; v?: VerificationData }) {
  const [popup, setPopup] = useState(true);
  const conditions = (v?.conditions ?? []).map((c) => ({ id: c.id, text: c.text }));
  if (!d.ir) return <p className="notice">이 설계에는 모의 실행에 필요한 회로 데이터가 없어요.</p>;
  return (
    <section className="block">
      {popup && (
        <div className="modal-back" onClick={() => setPopup(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h3>⚠ 실제 프로그램으로 확인하세요</h3>
            <p>회로 논리가 맞는지 판별하는 모의 시뮬레이션이에요.<br /><strong className="warn-line">GX Works 등 실제 프로그램에서 반드시 다시 확인하세요.</strong></p>
            <button onClick={() => setPopup(false)}>확인</button>
          </div>
        </div>
      )}
      <Suspense fallback={<p className="notice">모의 실행 화면을 불러오는 중…</p>}>
        <PlcSimulator ir={d.ir} io={d.io_used} conditions={conditions} assumptions={d.assumptions} />
      </Suspense>
    </section>
  );
}

// GX Works2의 "Write to CSV File"이 만드는 형식(UTF-16 탭 구분)을 따라 만든다.
function downloadCsv(il: string[], cpu?: string) {
  const q = (s: string) => `"${s}"`;
  const model = (cpu ?? "").replace(/CPU$/, "");
  const rows = [
    q("(Untitled Project)"),
    [q("PLC Information:"), q(`QCPU (Q mode)${model ? " " + model : ""}`)].join("\t"),
    ["Step No.", "Line Statement", "Instruction", "I/O(Device)", "Blank", "PI Statement", "Note"].map(q).join("\t"),
    ...il.map((line, i) => {
      const [op, ...rest] = line.trim().split(/\s+/);
      return [String(i), "", op, rest.join(" "), "", "", ""].map(q).join("\t");
    }),
  ];
  const text = rows.join("\r\n") + "\r\n";
  const buf = new Uint16Array(text.length + 1);
  buf[0] = 0xfeff;
  for (let i = 0; i < text.length; i++) buf[i + 1] = text.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([buf], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "circuit-gxworks2.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export function DownloadPanel({ d, cpu }: { d: DesignData; cpu?: string }) {
  const [guide, setGuide] = useState(false);
  return (
    <section className="block">
      <p className="notice">자동 생성된 초안이에요. 실제 장비에 넣기 전에 반드시 GX Works2 등 실제 프로그램에서 확인하세요.</p>
      <div className="folds">
        <Fold title="명령어(IL) 보기"><pre>{d.il.join("\n")}</pre></Fold>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 14, marginTop: 14 }}>
        <button type="button" className="btn primary" onClick={() => downloadCsv(d.il, cpu)}>GX Works2 파일 받기 (.csv)</button>
        <button type="button" className="btn primary" onClick={() => setGuide(true)}>GX Works2에서 여는 방법 보기</button>
      </div>
      {guide && <GxGuide onClose={() => setGuide(false)} />}
    </section>
  );
}

export function Design({ d }: { d: DesignData }) {
  return (
    <section className="block">
      <h3>설계 결과</h3>
      <p className="notice">자동 생성된 초안이에요. 실제 장비에 넣기 전에 반드시 사람이 확인하세요.</p>

      <h4>회로 동작 설명</h4>
      <ol className="rungs">
        {d.explanation.map((x) => (
          <li key={x.rung_id}>
            <span className="rung-id">{x.rung_id}</span>
            <span className="rung-text">{x.text}</span>
            <span className="rung-conds">{x.condition_ids.map((c) => <span key={c} className="chip">{c}</span>)}</span>
          </li>
        ))}
      </ol>

      <h4>사용한 입출력</h4>
      <div className="table-wrap">
        <table className="io-table">
          <thead><tr><th>주소</th><th>이름</th><th>종류</th><th>설명</th></tr></thead>
          <tbody>
            {d.io_used.map((r) => (
              <tr key={r.device}><td><code>{r.device}</code></td><td>{r.name}</td><td>{r.kind}</td><td>{r.desc}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="notice">푸시버튼은 설정한 종류대로 NO는 a접점, NC는 b접점으로 설계돼요. 누르면 ON이라 GX Simulator2에서도 안 눌렀을 때(OFF)부터 그대로 시험할 수 있어요.</p>

      <div className="folds">
        <Fold title="명령어(IL) 보기">
          <pre>{d.il.join("\n")}</pre>
          <p className="notice">GX Works2용 파일은 마지막 단계 "파일 받기"에서 받을 수 있어요.</p>
        </Fold>
        {d.assumptions.length > 0 && <Fold title="가정" count={d.assumptions.length}><ul>{d.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></Fold>}
        {d.limitations.length > 0 && <Fold title="제한 사항" count={d.limitations.length}><ul>{d.limitations.map((a) => <li key={a}>{a}</li>)}</ul></Fold>}
      </div>
    </section>
  );
}

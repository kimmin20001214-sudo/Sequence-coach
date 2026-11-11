import { lazy, Suspense, useState } from "react";
import type { JobStatus } from "./api";
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
  PASS: { icon: "??, label: "?듦낵", cls: "ok" },
  FAIL: { icon: "??, label: "?ㅽ뙣", cls: "bad" },
  UNVERIFIED: { icon: "!", label: "寃利?紐???, cls: "warn" },
} as const;

export function Stepper({ steps, current, failed }: { steps: { key: string; label: string }[]; current: number; failed: boolean }) {
  return (
    <ol className="run-stepper" aria-label="吏꾪뻾 ?④퀎">
      {steps.map((s, i) => (
        <li key={s.key} className={i < current ? "done" : i === current ? (failed ? "fail" : "now") : ""} aria-current={i === current ? "step" : undefined}>
          <span className="dot">{i < current ? "?? : failed && i === current ? "?? : i + 1}</span>
          <span className="lbl">{s.label}</span>
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
        <span className="summary-icon">{ok ? "?? : "!"}</span>
        <div>
          <strong>{ok ? "紐⑤뱺 議곌굔??寃利앹쓣 ?듦낵?덉뼱?? : escalated ? "?먮룞 ?섏젙???ㅽ뙣?덉뼱??쨌 ?щ엺???뺤씤??二쇱꽭?? : "寃利앹쓣 ?듦낵?섏? 紐삵븳 議곌굔???덉뼱??}</strong>
          <div className="summary-sub">?쒕쾭媛 ?뚮줈瑜?紐⑥쓽 ?ㅽ뻾?댁꽌 議곌굔???섎굹???뺤씤??寃곌낵?덉슂.</div>
        </div>
      </div>
      <div className="stats">
        <div><b>{pass}/{total}</b><span>?듦낵??議곌굔</span></div>
        {unverified > 0 && <div><b>{unverified}</b><span>寃利?紐???議곌굔</span></div>}
        <div><b>{fixCount}</b><span>?먮룞 ?섏젙 ?쒕룄</span></div>
      </div>
    </div>
  );
}

export function Conditions({ v }: { v: VerificationData }) {
  return (
    <section className="block">
      <h3>議곌굔蹂?寃利?寃곌낵</h3>
      <ul className="cond-list">
        {v.conditions.map((c) => {
          const s = STATUS[c.status];
          return (
            <li key={c.id} className={`cond ${s.cls}`}>
              <span className="cond-id">{c.id}</span>
              <div className="cond-body">
                <div className="cond-text">{c.text}</div>
                {c.message && <div className="cond-msg">{c.message}{c.rung_id && ` 쨌 ??${c.rung_id}`}</div>}
                {c.notes.map((n) => <div key={n} className="cond-note">{n}</div>)}
              </div>
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
      <h3>?먮룞 ?섏젙 湲곕줉</h3>
      <ul className="fix-list">
        {events.map((e, i) => {
          const diff = e.data.diff as Diff | undefined;
          const ok = e.kind === "fix_applied";
          return (
            <li key={i} className={ok ? "ok" : "bad"}>
              <div className="fix-head"><span className={`pill ${ok ? "ok" : "bad"}`}>{ok ? "?섏젙 ?깃났" : "?섏젙 嫄곕?"}</span> {String(e.data.reason)}</div>
              {ok && e.data.agent_reason ? <div className="cond-msg">?섏젙 ?댁쑀: {String(e.data.agent_reason)}</div> : null}
              {diff && (
                <ul className="diff">
                  {diff.changed.map((c) => <li key={c.rung_id}>??{c.rung_id}: {c.summary}</li>)}
                  {diff.added.map((r) => <li key={"a" + r}>??{r} 異붽?</li>)}
                  {diff.removed.map((r) => <li key={"r" + r}>??{r} ??젣</li>)}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      <p className="notice">?섏젙???깃났?덈뒗吏??AI媛 ?꾨땲???쒕쾭媛 紐⑤뱺 議곌굔???ㅼ떆 紐⑥쓽 ?ㅽ뻾?댁꽌 ?뺤씤?댁슂.</p>
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
  if (!d.ir) return <p className="notice">???ㅺ퀎?먮뒗 紐⑥쓽 ?ㅽ뻾???꾩슂???뚮줈 ?곗씠?곌? ?놁뼱??</p>;
  return (
    <section className="block">
      {popup && (
        <div className="modal-back" onClick={() => setPopup(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h3>???ㅼ젣 ?꾨줈洹몃옩?쇰줈 ?뺤씤?섏꽭??/h3>
            <p>???붾㈃??紐⑥쓽 ?ㅽ뻾? 李멸퀬?⑹씠?먯슂. ?ㅼ젣 ?ㅻ퉬???곸슜?섍린 ?꾩뿉 GX Works ???ㅼ젣 ?꾨줈洹몃옩?먯꽌 諛섎뱶???ㅼ떆 ?뺤씤?섏꽭??</p>
            <button onClick={() => setPopup(false)}>?뺤씤</button>
          </div>
        </div>
      )}
      <Suspense fallback={<p className="notice">紐⑥쓽 ?ㅽ뻾 ?붾㈃??遺덈윭?ㅻ뒗 以묅?/p>}>
        <PlcSimulator ir={d.ir} io={d.io_used} conditions={conditions} assumptions={d.assumptions} />
      </Suspense>
    </section>
  );
}

export function Design({ d }: { d: DesignData }) {
  return (
    <section className="block">
      <h3>?ㅺ퀎 寃곌낵</h3>
      <p className="notice">?먮룞 ?앹꽦??珥덉븞?댁뿉?? ?ㅼ젣 ?λ퉬???ｊ린 ?꾩뿉 諛섎뱶???щ엺???뺤씤?섏꽭??</p>

      <h4>?뚮줈 ?숈옉 ?ㅻ챸</h4>
      <ol className="rungs">
        {d.explanation.map((x) => (
          <li key={x.rung_id}>
            <span className="rung-id">{x.rung_id}</span>
            <span className="rung-text">{x.text}</span>
            <span className="rung-conds">{x.condition_ids.map((c) => <span key={c} className="chip">{c}</span>)}</span>
          </li>
        ))}
      </ol>

      <h4>?ъ슜???낆텧??/h4>
      <div className="table-wrap">
        <table className="io-table">
          <thead><tr><th>二쇱냼</th><th>?대쫫</th><th>醫낅쪟</th><th>?ㅻ챸</th></tr></thead>
          <tbody>
            {d.io_used.map((r) => (
              <tr key={r.device}><td><code>{r.device}</code></td><td>{r.name}</td><td>{r.kind}</td><td>{r.desc}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="folds">
        <Fold title="紐낅졊??IL) 蹂닿린"><pre>{d.il.join("\n")}</pre></Fold>
        {d.assumptions.length > 0 && <Fold title="媛?? count={d.assumptions.length}><ul>{d.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></Fold>}
        {d.limitations.length > 0 && <Fold title="?쒗븳 ?ы빆" count={d.limitations.length}><ul>{d.limitations.map((a) => <li key={a}>{a}</li>)}</ul></Fold>}
      </div>
    </section>
  );
}

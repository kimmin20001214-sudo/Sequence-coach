import type { ReactNode } from "react";

export function Card({ title, desc, children }: { title: string; desc?: string; children: ReactNode }) {
  return (
    <section className="card">
      <header className="card-head">
        <h2>{title}</h2>
        {desc && <p>{desc}</p>}
      </header>
      {children}
    </section>
  );
}

export function Field({
  label, required, error, hint, group, children,
}: { label: string; required?: boolean; error?: string; hint?: string; group?: boolean; children: ReactNode }) {
  const Tag = group ? "div" : "label";
  return (
    <Tag className={"field" + (error ? " has-error" : "")}>
      <span className="field-label">
        {label}
        {required && <b className="req">필수</b>}
      </span>
      {children}
      {error ? <span className="msg err">{error}</span> : hint ? <span className="msg">{hint}</span> : null}
    </Tag>
  );
}

export function Chips({
  options, selected, onToggle,
}: { options: string[]; selected: string[]; onToggle: (o: string, on: boolean) => void }) {
  return (
    <div className="chips">
      {options.map((o) => {
        const on = selected.includes(o);
        return (
          <button key={o} type="button" className={"chip" + (on ? " on" : "")} aria-pressed={on} onClick={() => onToggle(o, !on)}>
            {on ? "✓ " : ""}{o}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  options, value, onChange,
}: { options: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="segmented" role="radiogroup">
      {options.map(([v, l]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {l}
        </button>
      ))}
    </div>
  );
}

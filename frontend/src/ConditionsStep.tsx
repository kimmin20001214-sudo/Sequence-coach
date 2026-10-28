import type { Condition } from "./spec";
import { Card } from "./ui";

interface Props {
  conditions: Condition[];
  setConditions: (c: Condition[]) => void;
  error: string;
  onBack: () => void;
  onSave: () => void;
}

export default function ConditionsStep({ conditions, setConditions, error, onBack, onSave }: Props) {
  const set = (i: number, patch: Partial<Condition>) =>
    setConditions(conditions.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const remove = (i: number) => {
    const next = conditions.filter((_, idx) => idx !== i);
    setConditions(next.length ? next : [{ text: "", must_pass: true }]);
  };
  return (
    <>
      <Card title="동작 조건" desc="PLC가 어떻게 동작해야 하는지 한 줄씩 적고, 반드시 만족해야 하는 조건은 '필수'로 표시해요.">
        <p className="example">예) START 버튼을 누르면 모터가 켜지고, 비상정지를 누르면 모든 출력이 꺼진다.</p>
        <div className="conds">
          {conditions.map((c, i) => (
            <div className="cond" key={i}>
              <span className="cond-no">C{i + 1}</span>
              <input value={c.text} placeholder="조건을 한 줄로 적어 주세요" onChange={(e) => set(i, { text: e.target.value })} />
              <button type="button" className={"chip" + (c.must_pass ? " on" : "")} aria-pressed={c.must_pass} onClick={() => set(i, { must_pass: !c.must_pass })}>
                {c.must_pass ? "필수" : "선택"}
              </button>
              <button type="button" className="icon-btn" aria-label="조건 삭제" onClick={() => remove(i)}>✕</button>
            </div>
          ))}
        </div>
        {error && <div className="banner err">{error}</div>}
        <button type="button" className="btn ghost" onClick={() => setConditions([...conditions, { text: "", must_pass: true }])}>＋ 조건 추가</button>
      </Card>
      <div className="actions">
        <button type="button" className="btn ghost" onClick={onBack}>← 이전</button>
        <button type="button" className="btn primary" onClick={onSave}>저장</button>
      </div>
    </>
  );
}

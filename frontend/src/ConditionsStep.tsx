import type { Condition } from "./spec";
import { Card } from "./ui";

interface Props {
  conditions: Condition[];
  setConditions: (c: Condition[]) => void;
  error: string;
  saving: boolean;
  onBack: () => void;
  onSave: () => void;
}

const TIPS = [
  ["신호 이름으로 쓰기", "입출력 목록의 이름(START_PB, MOTOR)을 그대로 써야 에이전트가 정확히 찾아요."],
  ["한 줄에 하나씩", "조건 하나당 한 문장. 길면 나눠서 적으면 검증도 쉬워요."],
  ["순서·시간 구체적으로", "\"잠시 후\" 대신 \"3초 후\"처럼 숫자로 적어요."],
  ["안전·인터록 빠뜨리지 않기", "동시에 켜지면 안 되는 출력, 비상정지 때 동작을 꼭 적어요."],
  ["필수 vs 선택", "꼭 지켜야 하는 것만 필수로 두세요. 필수 조건은 검증에서 반드시 통과해야 해요."],
];

const EXAMPLES = [
  "START_PB를 누르면 MOTOR가 켜지고 손을 떼도 유지된다 (자기유지).",
  "STOP_PB를 누르면 MOTOR가 꺼진다.",
  "SENSOR가 물체를 감지하면 CONVEYOR가 멈추고, 물체가 사라지면 3초 후 다시 가동한다.",
  "SOL_FWD와 SOL_BWD는 동시에 켜지지 않는다 (인터록).",
  "EMG가 눌리면 모든 출력이 꺼지고, 해제 후 START_PB를 다시 눌러야 기동한다.",
  "MOTOR가 10초 이상 연속 가동되면 LAMP가 깜박인다.",
];

export default function ConditionsStep({ conditions, setConditions, error, saving, onBack, onSave }: Props) {
  const set = (i: number, patch: Partial<Condition>) =>
    setConditions(conditions.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const remove = (i: number) => {
    const next = conditions.filter((_, idx) => idx !== i);
    setConditions(next.length ? next : [{ text: "", must_pass: true }]);
  };
  const addExample = (text: string) => {
    const empty = conditions.findIndex((c) => !c.text.trim());
    if (empty >= 0) set(empty, { text });
    else setConditions([...conditions, { text, must_pass: true }]);
  };
  return (
    <>
      <Card title="동작 조건" desc="PLC가 어떻게 동작해야 하는지 한 줄씩 적고, 반드시 만족해야 하는 조건은 '필수'로 표시해요.">
        <details className="guide">
          <summary>작성 가이드 보기</summary>
          <ul>
            {TIPS.map(([t, d]) => <li key={t}><b>{t}</b> {d}</li>)}
          </ul>
          <p className="hint">예시를 누르면 조건에 추가돼요. 신호 이름은 내 설비에 맞게 고쳐 주세요.</p>
          <div className="chips">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="chip" onClick={() => addExample(ex)}>＋ {ex}</button>
            ))}
          </div>
        </details>
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
        <button type="button" className="btn primary" disabled={saving} onClick={onSave}>{saving ? "저장 중…" : "저장"}</button>
      </div>
    </>
  );
}

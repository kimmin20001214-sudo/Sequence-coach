import { useState } from "react";

const ITEMS: { icon: string; title: string; text: string }[] = [
  { icon: "1", title: "규칙에 맞는지", text: "주소 중복, 범위 초과, 타이머·카운터 값, 같은 출력을 두 번 쓰는지 확인해요." },
  { icon: "2", title: "조건대로 움직이는지", text: "내가 적은 조건마다 시험을 돌려서, 정해진 시각에 켜지고 꺼지는지 확인해요." },
  { icon: "3", title: "위험하게 움직이지 않는지", text: "아무것도 안 눌렀는데 켜지거나, 정지를 눌렀는데 켜져 있지 않은지 확인해요." },
];

export function CriteriaButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="criteria-btn" onClick={() => setOpen(true)}>📋 검증 기준 보기</button>
      {open && (
        <div className="modal-back" onClick={() => setOpen(false)}>
          <div className="modal criteria" role="dialog" aria-modal="true" aria-label="검증 기준" onClick={(e) => e.stopPropagation()}>
            <h3>이렇게 검증해요</h3>
            <ol className="criteria-list">
              {ITEMS.map((i) => (
                <li key={i.title}>
                  <span className="criteria-no">{i.icon}</span>
                  <div><strong>{i.title}</strong><p>{i.text}</p></div>
                </li>
              ))}
            </ol>
            <p className="criteria-lead">필수 조건이 하나라도 틀리면 실패이고, 선택 조건은 경고만 해요.<br />모의 실행 통과가 실제 설비의 안전을 보장하지는 않아요.</p>
            <button type="button" onClick={() => setOpen(false)}>닫기</button>
          </div>
        </div>
      )}
    </>
  );
}

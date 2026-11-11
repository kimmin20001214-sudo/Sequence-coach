import { useState } from "react";

interface Item { title: string; text: string }

const OVERVIEW: Item[] = [
  { title: "규칙에 맞는지", text: "주소 중복, 범위 초과, 타이머·카운터 값, 같은 출력을 두 번 쓰는지 확인해요." },
  { title: "조건대로 움직이는지", text: "내가 적은 조건마다 시험을 돌려서, 정해진 시각에 켜지고 꺼지는지 확인해요." },
  { title: "위험하게 움직이지 않는지", text: "아무것도 안 눌렀는데 켜지거나, 정지를 눌렀는데 켜져 있지 않은지 확인해요." },
];

const DETAIL: Item[] = [
  { title: "자기유지 (누르면 켜지고 유지)", text: "시작을 누르면 켜지고, 손을 떼도 유지되고, 정지를 누르면 꺼지는지 봐요. 정지를 누른 채 시작해도 안 켜져야 해요." },
  { title: "정지 우선", text: "정지를 누른 상태에서는 다른 버튼을 전부 눌러도 출력이 꺼져 있는지 봐요." },
  { title: "ON 지연 (몇 초 뒤에 켜짐)", text: "정해진 시간 전에는 꺼져 있고, 시간이 지나면 켜지는지 봐요. 중간에 정지하면 꺼져야 해요." },
  { title: "일정 시간만 ON", text: "켜진 뒤 정해진 시간이 지나면 저절로 꺼지는지 봐요." },
  { title: "인터록 (동시에 켜지면 안 됨)", text: "입력을 여러 방식으로 눌러 봐도 두 출력이 동시에 켜지지 않는지 봐요." },
  { title: "표시등", text: "램프가 대상 출력과 항상 같이 켜지고 꺼지는지 봐요." },
  { title: "AND 조건 (모두 눌러야 켜짐)", text: "모두 눌렀을 때만 켜지고, 하나라도 빠지면 꺼져 있는지 봐요." },
  { title: "OR 조건 (하나만 눌러도 켜짐)", text: "아무것도 안 누르면 꺼져 있고, 어느 하나만 눌러도 켜지는지 봐요." },
  { title: "SET / RESET", text: "세트를 누르면 켜져서 유지되고, 리셋을 누르면 꺼지는지 봐요." },
  { title: "직접 쓴 시험", text: "정해진 틀로 표현하기 어려운 조건이에요. 에이전트가 직접 시험을 써서 신뢰도가 낮다고 표시돼요." },
  { title: "자동 안전 탐색", text: "시험과 별개로 입력을 자동으로 바꿔 봐요. 아무것도 안 눌렀는데 켜지는지, 비상정지 중에 켜져 있는지, 한 번도 안 켜지는 출력이 있는지 확인해요." },
];

function List({ items }: { items: Item[] }) {
  return (
    <ol className="criteria-list">
      {items.map((i, n) => (
        <li key={i.title}>
          <span className="criteria-no">{n + 1}</span>
          <div><strong>{i.title}</strong><p>{i.text}</p></div>
        </li>
      ))}
    </ol>
  );
}

export function CriteriaButton() {
  const [open, setOpen] = useState<"" | "overview" | "detail">("");
  const close = () => setOpen("");
  return (
    <>
      <div className="criteria-btns">
        <button type="button" className="criteria-btn" onClick={() => setOpen("overview")}>📋 검증 기준 보기</button>
        <button type="button" className="criteria-btn" onClick={() => setOpen("detail")}>🔎 조건별 검증 기준 보기</button>
      </div>
      {open && (
        <div className="modal-back" onClick={close}>
          <div className="modal criteria" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h3>{open === "overview" ? "이렇게 검증해요" : "조건별 검증 기준"}</h3>
            {open === "detail" && <p className="criteria-lead criteria-top">조건 종류마다 이런 시험을 해요.</p>}
            <div className="criteria-scroll">
              <List items={open === "overview" ? OVERVIEW : DETAIL} />
            </div>
            {open === "overview" && (
              <p className="criteria-lead">필수 조건이 하나라도 틀리면 실패이고, 선택 조건은 경고만 해요.<br />모의 실행 통과가 실제 설비의 안전을 보장하지는 않아요.</p>
            )}
            <button type="button" onClick={close}>닫기</button>
          </div>
        </div>
      )}
    </>
  );
}

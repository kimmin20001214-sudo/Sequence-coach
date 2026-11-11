import { useState } from "react";

const SECTIONS: { title: string; note: string; rows: [string, string][] }[] = [
  {
    title: "① 사전 규칙 검사",
    note: "하나라도 걸리면 실패이고, 동작 검사는 하지 않아요.",
    rows: [
      ["PLC 설정", "Q시리즈·호환 CPU·래더·GX Works2/GX Developer만 지원해요. 타이머는 100ms 단위만 돼요."],
      ["I/O 주소", "중복되거나, 설정한 점수를 넘거나, 목록에 없으면 실패예요."],
      ["내부 주소(M/T/C)", "정해진 범위를 벗어나면 실패예요."],
      ["설정값", "타이머·카운터 모두 K1~K32767 범위여야 해요."],
      ["형식", "렁 ID 중복, 출력 주소 종류 불일치, 허용되지 않은 명령어를 검사해요."],
      ["이중 코일", "같은 출력을 두 렁에서 켜면 실패예요. SET/RST 쌍은 허용해요."],
    ],
  },
  {
    title: "② 조건별 시험",
    note: "조건마다 시험 대본을 모의 실행해 정해진 시각의 ON/OFF를 기대값과 비교해요. 필수 조건 실패는 전체 실패, 선택 조건 실패는 경고예요.",
    rows: [
      ["자기유지", "시작하면 켜지고, 놓아도 유지되고, 정지하면 꺼져요. 정지 중에는 시작해도 안 켜져요."],
      ["정지 우선", "정지를 누른 상태에서는 다른 입력을 다 눌러도 출력이 꺼져 있어요."],
      ["ON 지연", "지연 시간 전에는 꺼져 있고 지난 뒤에 켜져요."],
      ["일정 시간 ON", "켜진 뒤 정해진 시간이 지나면 꺼져요."],
      ["인터록", "두 출력이 동시에 켜지지 않아요."],
      ["표시등", "램프가 대상 출력과 항상 같아요."],
      ["AND / OR 조건", "AND는 모두 눌러야 켜지고, OR은 하나만 눌러도 켜져요."],
      ["SET / RESET", "세트하면 켜지고 리셋하면 꺼져요."],
      ["직접 쓴 대본", "에이전트가 직접 쓴 시나리오예요. 신뢰도가 낮다고 표시돼요."],
    ],
  },
  {
    title: "③ 자동 안전 탐색",
    note: "시나리오가 부족해도 걸러내려고 입력을 자동으로 바꿔 봐요. 결과는 항상 같아요.",
    rows: [
      ["자동 켜짐", "아무것도 안 눌렀는데 출력이 켜지면 실패예요."],
      ["정지 우선", "정지·비상정지를 누른 동안 출력이 켜져 있으면 문제예요. 비상정지는 실패, 일반 정지는 경고예요."],
      ["죽은 출력", "입력을 여러 방식으로 바꿔도 한 번도 안 켜지는 출력을 알려줘요. 필수 조건과 관련되면 실패예요."],
    ],
  },
  {
    title: "④ 보강 경고",
    note: "",
    rows: [["검증 범위", "조건이 말한 신호를 시나리오가 한 번도 안 건드렸으면 검증이 부족할 수 있다고 알려줘요."]],
  },
];

export function CriteriaButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="criteria-btn" onClick={() => setOpen(true)}>📋 검증 기준 보기</button>
      {open && (
        <div className="modal-back" onClick={() => setOpen(false)}>
          <div className="modal criteria" role="dialog" aria-modal="true" aria-label="검증 기준표" onClick={(e) => e.stopPropagation()}>
            <h3>검증 기준표</h3>
            <p className="criteria-lead">서버가 AI 없이 코드로 판정해요. 모의 실행 통과는 실제 설비의 안전을 보장하지 않아요.</p>
            <div className="criteria-body">
              {SECTIONS.map((s) => (
                <section key={s.title}>
                  <h4>{s.title}</h4>
                  {s.note && <p className="criteria-note">{s.note}</p>}
                  <table>
                    <tbody>
                      {s.rows.map(([k, v]) => (<tr key={k}><th>{k}</th><td>{v}</td></tr>))}
                    </tbody>
                  </table>
                </section>
              ))}
            </div>
            <button type="button" onClick={() => setOpen(false)}>닫기</button>
          </div>
        </div>
      )}
    </>
  );
}

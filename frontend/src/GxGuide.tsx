import { useState } from "react";

// 스크린샷은 frontend/public/guide/ 에 step1.png ... 이름으로 넣으면 자동으로 보여요.
const STEPS = [
  { title: "새 프로젝트 만들기", text: "GX Works2에서 새 프로젝트를 만들어요. 프로젝트 종류는 Simple Project, 시리즈는 QCPU (Q mode), 기종은 설계 때 입력한 CPU(예: Q03UD), 언어는 Ladder로 골라요.", img: "step1.png" },
  { title: "CSV 읽기 메뉴", text: "위쪽 메뉴에서 Edit → Read from CSV File을 눌러요.", img: "step2.png" },
  { title: "받은 CSV 파일 선택", text: "'파일 받기'에서 받은 .csv 파일을 찾아서 열어요. 읽고 나서 래더로 바뀌지 않으면 F4(변환)를 눌러요.", img: "step3.png" },
  { title: "시뮬레이션 시작 버튼", text: "도구 모음에서 빨간 네모로 표시한 시뮬레이션 시작 버튼을 눌러요.", img: "step4.png" },
  { title: "시뮬레이터 정상 작동 확인", text: "GX Simulator2 창이 뜨고 RUN이 선택되어 MODE와 RUN LED가 초록색이면 정상이에요.", img: "step5.png" },
  { title: "시뮬레이션 화면 (동작 전)", text: "입력이 모두 OFF라서 접점이 비어 있고 출력(Y0)도 꺼져 있어요.", img: "step6.png" },
  { title: "시뮬레이션 화면 (동작 중)", text: "접점을 선택하고 Shift + Enter를 누르면 그 디바이스를 ON/OFF할 수 있어요. 켜지면 파란색으로 채워지고 출력도 따라 켜져요.", img: "step7.png" },
];

export function GxGuide({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const [missing, setMissing] = useState(false);
  const s = STEPS[i];
  const go = (n: number) => { setI(n); setMissing(false); };
  return (
    <div className="gxg-back" onClick={onClose}>
      <div className="gxg" role="dialog" aria-label="GX Works2 사용 방법" onClick={(e) => e.stopPropagation()}>
        <div className="gxg-head">
          <b>GX Works2에서 여는 방법</b>
          <button type="button" className="gxg-x" onClick={onClose} aria-label="닫기">×</button>
        </div>
        <h3>{i + 1}. {s.title}</h3>
        {missing ? (
          <div className="gxg-ph">스크린샷 준비 중 (public/guide/{s.img})</div>
        ) : (
          <img key={s.img} className="gxg-img" src={`/guide/${s.img}`} alt={s.title} onError={() => setMissing(true)} />
        )}
        <p>{s.text}</p>
        <div className="gxg-nav">
          <button type="button" className="btn ghost" disabled={i === 0} onClick={() => go(i - 1)}>← 이전</button>
          <span>{i + 1} / {STEPS.length}</span>
          {i < STEPS.length - 1
            ? <button type="button" className="btn primary" onClick={() => go(i + 1)}>다음 →</button>
            : <button type="button" className="btn primary" onClick={onClose}>닫기</button>}
        </div>
      </div>
    </div>
  );
}

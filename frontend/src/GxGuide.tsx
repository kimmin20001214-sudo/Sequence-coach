import { useState } from "react";

// 스크린샷은 frontend/public/guide/ 에 step1.png ... 이름으로 넣으면 자동으로 보여요.
const STEPS = [
  { title: "새 프로젝트 만들기", text: "GX Works2에서 새 프로젝트를 만들어요. 시리즈는 QCPU(Q모드), 기종은 설계 때 입력한 CPU(예: Q03UD), 언어는 래더로 골라요.", img: "step1.png" },
  { title: "CSV 파일 열기 메뉴", text: "메뉴에서 Edit → Read from CSV File을 눌러요.", img: "step2.png" },
  { title: "받은 파일 선택", text: "'파일 받기'에서 받은 .csv 파일을 골라 열어요.", img: "step3.png" },
  { title: "래더로 변환", text: "읽은 명령어를 래더로 바꾸려면 F4를 눌러요. 오류 메시지가 없는지 확인해요.", img: "step4.png" },
  { title: "GX Simulator2로 시험", text: "시뮬레이터를 켜고 입력을 ON/OFF 해 보며 출력이 설계대로 움직이는지 확인해요. 정지 버튼은 누르면 ON이에요.", img: "step5.png" },
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

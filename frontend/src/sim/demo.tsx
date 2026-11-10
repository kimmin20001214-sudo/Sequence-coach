import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './../index.css'
import PlcSimulator from './PlcSimulator'
import { SAMPLES } from './samples'
import './sim.css'

// 홈페이지에 연결하기 전 확인용 단독 페이지(/simulator.html).
function Demo() {
  const [key, setKey] = useState(SAMPLES[0].key)
  const s = SAMPLES.find((x) => x.key === key)!
  return (
    <div className="sim-demo">
      <h1>PLC 모의 시뮬레이터 (미리보기)</h1>
      <p className="lead">예시 회로를 골라 입력 버튼을 눌러 보세요. 아직 홈페이지에는 연결되지 않은 화면이에요.</p>
      <div className="sim-tabs">
        {SAMPLES.map((x) => (
          <button key={x.key} type="button" className={'sim-chip' + (x.key === key ? ' on' : '')} onClick={() => setKey(x.key)}>
            {x.title}
          </button>
        ))}
      </div>
      <PlcSimulator key={s.key} ir={s.ir} io={s.io} conditions={s.conditions} assumptions={s.assumptions} />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Demo />
  </StrictMode>,
)

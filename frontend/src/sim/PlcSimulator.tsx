import { useEffect, useMemo, useRef, useState } from 'react'
import type { Condition, Ir, IoRow } from './engine'
import { SCAN_MS, advance, inputRows, internalDevices, newState, outputRows, readDevice, snapshot } from './engine'
import { RungView } from './LadderView'
import './sim.css'

type Props = {
  ir: Ir
  io: IoRow[]
  conditions?: Condition[]
  assumptions?: string[]
}

type LogItem = { t: number; text: string; on: boolean }

const TICK_MS = 50
const fmt = (ms: number) => `${(ms / 1000).toFixed(1)}초`

export default function PlcSimulator({ ir, io, conditions = [], assumptions = [] }: Props) {
  const ins = useMemo(() => inputRows(io), [io])
  const outs = useMemo(() => outputRows(io), [io])
  const inner = useMemo(() => internalDevices(ir, io), [ir, io])
  const nameOf = (d: string) => io.find((r) => r.device.toUpperCase() === d)?.name ?? d

  // active = 사용자가 누르는(켜는) 중. 평상시 ON인 b접점 입력은 누르면 OFF가 된다.
  const [active, setActive] = useState<Record<string, boolean>>({})
  const physical = useMemo(
    () => Object.fromEntries(ins.map((r) => [r.device, r.normallyOn ? !active[r.device] : !!active[r.device]])),
    [ins, active],
  )
  const physRef = useRef(physical)
  useEffect(() => {
    physRef.current = physical
  }, [physical])

  const [state, setState] = useState(() => advance(newState(), ir, io, physical, 10))
  const stateRef = useRef(state)
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [log, setLog] = useState<LogItem[]>([])
  const logRef = useRef(log)

  useEffect(() => {
    if (!running) return
    const id = setInterval(() => {
      let cur = stateRef.current
      const added: LogItem[] = []
      const watch = [...outs.map((o) => o.device), ...inner]
      // 10ms씩 나눠 계산해야 켜지고 꺼진 시각이 정확히 기록된다.
      for (let t = 0; t < TICK_MS * speed; t += SCAN_MS) {
        const prev = cur
        cur = advance(prev, ir, io, physRef.current, SCAN_MS)
        for (const d of watch) {
          const a = readDevice(d, prev)
          const b = readDevice(d, cur)
          if (a !== b) added.push({ t: cur.time, text: `${nameOf(d)} ${b ? '켜짐' : '꺼짐'}`, on: b })
        }
        for (const [d, tm] of Object.entries(cur.timers)) {
          const a = (prev.timers[d]?.elapsed ?? 0) >= tm.preset
          const b = tm.elapsed >= tm.preset
          if (a !== b) added.push({ t: cur.time, text: `타이머 ${d} ${b ? '시간 도달' : '초기화'}`, on: b })
        }
      }
      stateRef.current = cur
      setState(cur)
      if (added.length) {
        logRef.current = [...added.reverse(), ...logRef.current].slice(0, 40)
        setLog(logRef.current)
      }
    }, TICK_MS)
    return () => clearInterval(id)
  })

  const { rec, rungPower } = useMemo(() => snapshot(state, ir, io, physical), [state, ir, io, physical])

  const reset = () => {
    const s = advance(newState(), ir, io, physRef.current, 10)
    stateRef.current = s
    setState(s)
    logRef.current = []
    setLog([])
    setRunning(false)
  }

  const press = (d: string, v: boolean) => setActive((a) => (a[d] === v ? a : { ...a, [d]: v }))

  return (
    <div className="sim">
      <div className="sim-bar">
        <div className="sim-clock" aria-live="off">
          <span className="sim-clock-label">경과 시간</span>
          <strong>{fmt(state.time)}</strong>
        </div>
        <div className="sim-ctl">
          <button type="button" className={'sim-btn' + (running ? '' : ' play')} onClick={() => setRunning((r) => !r)}>
            {running ? '⏸ 일시정지' : state.time <= 10 ? '▶ 시작' : '▶ 계속'}
          </button>
          <button type="button" className="sim-btn" onClick={reset}>↺ 처음으로</button>
          <span className="sim-speed" role="group" aria-label="속도">
            {[1, 5, 10].map((v) => (
              <button key={v} type="button" className={'sim-chip' + (speed === v ? ' on' : '')} onClick={() => setSpeed(v)}>
                ×{v}
              </button>
            ))}
          </span>
        </div>
      </div>

      {!running && <p className="sim-hint">{state.time <= 10 ? '▶ 시작을 누르면 모의 실행이 시작돼요.' : '일시정지 중이에요. ▶ 계속을 누르면 다시 진행돼요.'}</p>}

      <div className="sim-grid">
        <section className="sim-card">
          <h3>1. 입력 <small>버튼을 누르고 있어 보세요</small></h3>
          <div className="sim-ins">
            {ins.map((r) => {
              const on = !!active[r.device]
              const common = {
                className: 'sim-input' + (on ? ' on' : ''),
                'aria-pressed': on,
              }
              return r.momentary ? (
                <button
                  key={r.device}
                  type="button"
                  {...common}
                  onPointerDown={(e) => {
                    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* 포인터를 잡지 못해도 누름은 처리한다 */ }
                    press(r.device, true)
                  }}
                  onPointerUp={() => press(r.device, false)}
                  onPointerCancel={() => press(r.device, false)}
                  onKeyDown={(e) => { if (e.key === ' ' || e.key === 'Enter') press(r.device, true) }}
                  onKeyUp={(e) => { if (e.key === ' ' || e.key === 'Enter') press(r.device, false) }}
                >
                  <b>{r.name}</b>
                  <span>{r.device} · {r.normallyOn ? '누르면 끊김(평상시 ON)' : '누르는 동안 ON'}</span>
                </button>
              ) : (
                <button key={r.device} type="button" {...common} onClick={() => press(r.device, !on)}>
                  <b>{r.name}</b>
                  <span>{r.device} · 스위치 {on ? 'ON' : 'OFF'}</span>
                </button>
              )
            })}
            {ins.length === 0 && <p className="sim-empty">입력(X) 장치가 없어요.</p>}
          </div>
        </section>

        <section className="sim-card">
          <h3>2. 출력 <small>회로 결과</small></h3>
          <div className="sim-outs">
            {outs.map((r) => {
              const on = readDevice(r.device, state)
              return (
                <div key={r.device} className={'sim-out' + (on ? ' on' : '')}>
                  <span className="sim-lamp" aria-hidden />
                  <div>
                    <b>{r.name}</b>
                    <span>{r.device} · {r.desc || r.kind}</span>
                  </div>
                  <em>{on ? '켜짐' : '꺼짐'}</em>
                </div>
              )
            })}
            {Object.entries(state.timers).map(([d, t]) => (
              <div key={d} className="sim-timer">
                <div className="sim-timer-top">
                  <b>타이머 {d}</b>
                  <span>{fmt(t.elapsed)} / {fmt(t.preset)}</span>
                </div>
                <div className="sim-prog"><i style={{ width: `${t.preset ? (t.elapsed / t.preset) * 100 : 0}%` }} className={t.elapsed >= t.preset ? 'done' : ''} /></div>
              </div>
            ))}
            {Object.entries(state.counters).map(([d, c]) => (
              <div key={d} className="sim-timer">
                <div className="sim-timer-top"><b>카운터 {d}</b><span>{c.count} / {c.preset}회</span></div>
              </div>
            ))}
            {inner.length > 0 && (
              <p className="sim-inner">내부 릴레이: {inner.map((d) => `${d} ${readDevice(d, state) ? 'ON' : 'OFF'}`).join(', ')}</p>
            )}
          </div>
        </section>
      </div>

      <section className="sim-card">
        <h3>3. 회로도 <small>전류가 흐르는 선은 초록색이에요</small></h3>
        {ir.rungs.map((rung) => (
          <div key={rung.id} className={'sim-rung' + (rungPower[rung.id] ? ' on' : '')}>
            <div className="sim-rung-head">
              <b>{rung.id}</b>
              <span>{rung.comment}</span>
              {(rung.covers ?? []).map((c) => (
                <em key={c} title={conditions.find((x) => x.id === c)?.text}>{c}</em>
              ))}
            </div>
            <div className="sim-scroll">
              <RungView rung={rung} io={io} rec={rec} power={!!rungPower[rung.id]} />
            </div>
          </div>
        ))}
      </section>

      <div className="sim-grid">
        <section className="sim-card">
          <h3>내 조건 확인표 <small>직접 눌러서 확인해 보세요</small></h3>
          <ul className="sim-conds">
            {conditions.map((c) => (
              <li key={c.id}><b>{c.id}</b> {c.text}</li>
            ))}
            {conditions.length === 0 && <li className="sim-empty">조건 정보가 없어요.</li>}
          </ul>
          {assumptions.length > 0 && (
            <div className="sim-assume">
              <b>가정한 내용</b>
              <ul>{assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
        </section>
        <section className="sim-card">
          <h3>동작 기록</h3>
          <ul className="sim-log">
            {log.map((l, i) => (
              <li key={i} className={l.on ? 'on' : ''}><time>{fmt(l.t)}</time> {l.text}</li>
            ))}
            {log.length === 0 && <li className="sim-empty">아직 변화가 없어요. 입력 버튼을 눌러 보세요.</li>}
          </ul>
        </section>
      </div>

      <p className="sim-note">
        이 화면은 설계된 회로를 바로 눌러 보는 모의 실행이에요. 실제 PLC와 완전히 같다고 보장하지 않으니, 설비에 적용하기 전에 GX Simulator 등으로 확인하고 사람이 검토해 주세요.
      </p>
    </div>
  )
}

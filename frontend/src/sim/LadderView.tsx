import type { ReactNode } from 'react'
import type { IoRow, Node, NodePower, Rung } from './engine'
import { deviceOf } from './engine'

const CW = 84 // 접점 칸 너비
const CH = 56 // 접점 칸 높이
const PAD = 14 // 병렬 묶음 좌우 여백
const OUT_W = 190
const ROW = 64

type Box = { w: number; h: number; mid: number }

function measure(n: Node): Box {
  if (n.type === 'contact') return { w: CW, h: CH, mid: CH / 2 }
  const kids = n.items.map(measure)
  if (n.type === 'AND') {
    const above = Math.max(...kids.map((k) => k.mid))
    const below = Math.max(...kids.map((k) => k.h - k.mid))
    return { w: kids.reduce((a, k) => a + k.w, 0), h: above + below, mid: above }
  }
  const h = kids.reduce((a, k) => a + k.h, 0)
  return { w: Math.max(...kids.map((k) => k.w)) + PAD * 2, h, mid: kids[0].mid }
}

type Ctx = { io: IoRow[]; rec: Map<Node, NodePower> }
const wire = (on: boolean) => (on ? 'lad-wire on' : 'lad-wire')

function draw(n: Node, x: number, y: number, ctx: Ctx, key: string, w?: number): ReactNode {
  const box = measure(n)
  const p = ctx.rec.get(n) ?? { inP: false, outP: false }
  const width = w ?? box.w
  const cy = y + box.mid

  if (n.type === 'contact') {
    const dev = deviceOf(n.signal, ctx.io)
    const label = ctx.io.find((r) => r.device.toUpperCase() === dev)?.name ?? n.signal
    const bar = 'lad-bar' + (p.outP ? ' on' : '')
    return (
      <g key={key}>
        <line className={wire(p.inP)} x1={x} y1={cy} x2={x + 26} y2={cy} />
        <line className={wire(p.outP)} x1={x + width - 26} y1={cy} x2={x + width} y2={cy} />
        <line className={bar} x1={x + 26} y1={cy - 11} x2={x + 26} y2={cy + 11} />
        <line className={bar} x1={x + width - 26} y1={cy - 11} x2={x + width - 26} y2={cy + 11} />
        {n.kind === 'NC' && <line className={bar} x1={x + 30} y1={cy + 11} x2={x + width - 30} y2={cy - 11} />}
        <text className="lad-label" x={x + width / 2} y={cy - 16} textAnchor="middle">{label}</text>
        <text className="lad-sub" x={x + width / 2} y={cy + 25} textAnchor="middle">{dev}{n.kind === 'NC' ? ' (b접점)' : ''}</text>
      </g>
    )
  }

  if (n.type === 'AND') {
    const extra = (width - box.w) / n.items.length
    let cx = x
    return (
      <g key={key}>
        {n.items.map((it, i) => {
          const b = measure(it)
          const iw = b.w + extra
          const el = draw(it, cx, y + box.mid - b.mid, ctx, `${key}.${i}`, iw)
          cx += iw
          return el
        })}
      </g>
    )
  }

  let ny = y
  const mids: number[] = []
  const kids = n.items.map((it, i) => {
    const b = measure(it)
    mids.push(ny + b.mid)
    const el = draw(it, x + PAD, ny, ctx, `${key}.${i}`, width - PAD * 2)
    ny += b.h
    return el
  })
  const last = mids[mids.length - 1]
  const R = x + width - PAD
  return (
    <g key={key}>
      {kids}
      {mids.map((m, i) => (
        <g key={i}>
          <line className={wire(p.inP)} x1={x} y1={m} x2={x + PAD} y2={m} />
          <line className={wire(ctx.rec.get(n.items[i])?.outP ?? false)} x1={R} y1={m} x2={R + PAD} y2={m} />
        </g>
      ))}
      <line className={wire(p.inP)} x1={x + PAD} y1={cy} x2={x + PAD} y2={last} />
      <line className={wire(p.outP)} x1={R} y1={cy} x2={R} y2={last} />
    </g>
  )
}

function outputText(o: Rung['outputs'][number], io: IoRow[]) {
  const d = deviceOf(o.target, io)
  const name = io.find((r) => r.device.toUpperCase() === d)?.name
  const head = name ? `${name} (${d})` : d
  if (o.kind === 'TON') return { head, tail: `타이머 ${(o.preset_ms ?? 0) / 1000}초` }
  if (o.kind === 'CTU') return { head, tail: `카운터 ${o.preset ?? 0}회` }
  return { head, tail: o.kind === 'SET' ? '켜 둠(SET)' : o.kind === 'RST' ? '끔(RST)' : '출력' }
}

export function RungView({ rung, io, rec, power }: { rung: Rung; io: IoRow[]; rec: Map<Node, NodePower>; power: boolean }) {
  const box = measure(rung.condition)
  const h = Math.max(box.h, rung.outputs.length * ROW) + 12
  const condW = Math.max(box.w, 120)
  const outX = 20 + condW + 40
  const W = outX + OUT_W + 12
  const baseY = box.mid + 6
  const ctx: Ctx = { io, rec }
  return (
    <svg className="lad-svg" viewBox={`0 0 ${W} ${h}`} width={W} height={h} role="img" aria-label={`${rung.id} 회로도`}>
      <line className="lad-rail" x1={4} y1={0} x2={4} y2={h} />
      <line className={wire(true)} x1={4} y1={baseY} x2={20} y2={baseY} />
      <g transform="translate(0,6)">{draw(rung.condition, 20, 0, ctx, rung.id, condW)}</g>
      <line className={wire(power)} x1={20 + condW} y1={baseY} x2={outX} y2={baseY} />
      {rung.outputs.map((o, i) => {
        const t = outputText(o, io)
        const oy = baseY + i * ROW
        return (
          <g key={i}>
            {i > 0 && <line className={wire(power)} x1={outX - 12} y1={baseY} x2={outX - 12} y2={oy} />}
            {i > 0 && <line className={wire(power)} x1={outX - 12} y1={oy} x2={outX} y2={oy} />}
            <rect className={'lad-coil' + (power ? ' on' : '')} x={outX} y={oy - 22} width={OUT_W} height={44} rx={22} />
            <text className="lad-coil-t" x={outX + OUT_W / 2} y={oy - 3} textAnchor="middle">{t.head}</text>
            <text className="lad-sub" x={outX + OUT_W / 2} y={oy + 13} textAnchor="middle">{t.tail}</text>
          </g>
        )
      })}
    </svg>
  )
}

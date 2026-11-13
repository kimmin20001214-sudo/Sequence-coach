// 회로(Ir)를 PLC처럼 스캔하며 계산하는 모의 엔진. 화면 확인용이며 실제 PLC와 같다고 보장하지 않는다.

export type Contact = { type: 'contact'; kind: 'NO' | 'NC'; signal: string }
export type Group = { type: 'AND' | 'OR'; items: Node[] }
export type Node = Contact | Group
export type Output = { kind: 'OUT' | 'SET' | 'RST' | 'TON' | 'CTU'; target: string; preset_ms?: number | null; preset?: number | null }
export type Rung = { id: string; comment?: string; condition: Node; outputs: Output[]; covers?: string[] }
export type Ir = { version: 1; rungs: Rung[] }
export type IoRow = { device: string; name: string; kind: string; desc?: string }
export type Condition = { id: string; text: string }

export const SCAN_MS = 10

export type SimState = {
  time: number
  dev: Record<string, boolean>
  timers: Record<string, { elapsed: number; preset: number }>
  counters: Record<string, { count: number; preset: number; prev: boolean }>
}

export type NodePower = { inP: boolean; outP: boolean }

export function newState(): SimState {
  return { time: 0, dev: {}, timers: {}, counters: {} }
}

export function deviceOf(signal: string, io: IoRow[]): string {
  const hit = io.find((r) => r.name.toUpperCase() === signal.toUpperCase())
  return (hit ? hit.device : signal).toUpperCase()
}

const isTimer = (d: string) => /^T\d+$/.test(d)
const isCounter = (d: string) => /^C\d+$/.test(d)

export function readDevice(d: string, s: SimState): boolean {
  if (isTimer(d)) {
    const t = s.timers[d]
    return !!t && t.elapsed >= t.preset
  }
  if (isCounter(d)) {
    const c = s.counters[d]
    return !!c && c.count >= c.preset
  }
  return !!s.dev[d]
}

// 접점마다 전류가 들어오고 나가는지 기록한다(회로도 색칠용).
export function evalNode(node: Node, inP: boolean, s: SimState, io: IoRow[], rec?: Map<Node, NodePower>): boolean {
  let outP: boolean
  if (node.type === 'contact') {
    const v = readDevice(deviceOf(node.signal, io), s)
    outP = inP && (node.kind === 'NO' ? v : !v)
  } else if (node.type === 'AND') {
    outP = node.items.reduce((p, it) => evalNode(it, p, s, io, rec), inP)
  } else {
    outP = node.items.map((it) => evalNode(it, inP, s, io, rec)).some(Boolean)
  }
  rec?.set(node, { inP, outP })
  return outP
}

function scanOnce(s: SimState, ir: Ir, io: IoRow[], dt: number) {
  for (const rung of ir.rungs) {
    const power = evalNode(rung.condition, true, s, io)
    for (const o of rung.outputs) {
      const d = deviceOf(o.target, io)
      if (o.kind === 'OUT') s.dev[d] = power
      else if (o.kind === 'SET') {
        if (power) s.dev[d] = true
      } else if (o.kind === 'RST') {
        if (power) {
          s.dev[d] = false
          if (s.timers[d]) s.timers[d].elapsed = 0
          if (s.counters[d]) s.counters[d].count = 0
        }
      } else if (o.kind === 'TON') {
        const t = (s.timers[d] ??= { elapsed: 0, preset: o.preset_ms ?? 0 })
        t.preset = o.preset_ms ?? 0
        t.elapsed = power ? Math.min(t.elapsed + dt, t.preset) : 0
      } else if (o.kind === 'CTU') {
        const c = (s.counters[d] ??= { count: 0, preset: o.preset ?? 0, prev: false })
        c.preset = o.preset ?? 0
        if (power && !c.prev) c.count += 1
        c.prev = power
      }
    }
  }
  s.time += dt
}

// 입력(X)은 화면에서 정한 값으로 덮어쓰고, 지정한 시간만큼 10ms씩 스캔한다.
export function advance(s: SimState, ir: Ir, io: IoRow[], inputs: Record<string, boolean>, ms: number): SimState {
  const next: SimState = {
    time: s.time,
    dev: { ...s.dev },
    timers: Object.fromEntries(Object.entries(s.timers).map(([k, v]) => [k, { ...v }])),
    counters: Object.fromEntries(Object.entries(s.counters).map(([k, v]) => [k, { ...v }])),
  }
  for (let t = 0; t < ms; t += SCAN_MS) {
    for (const [d, v] of Object.entries(inputs)) next.dev[d] = v
    scanOnce(next, ir, io, SCAN_MS)
  }
  return next
}

// 상태는 바꾸지 않고 현재 값으로 전류 흐름만 다시 계산한다.
export function snapshot(s: SimState, ir: Ir, io: IoRow[], inputs: Record<string, boolean>) {
  const view: SimState = { ...s, dev: { ...s.dev, ...inputs } }
  const rec = new Map<Node, NodePower>()
  const rungPower: Record<string, boolean> = {}
  for (const rung of ir.rungs) rungPower[rung.id] = evalNode(rung.condition, true, view, io, rec)
  return { rec, rungPower }
}

export function inputRows(io: IoRow[]) {
  return io.filter((r) => /^X/i.test(r.device)).map((r) => ({
    ...r,
    device: r.device.toUpperCase(),
    normallyOn: false,
    momentary: /푸시|버튼|push/i.test(r.kind),
  }))
}

export function outputRows(io: IoRow[]) {
  return io.filter((r) => /^Y/i.test(r.device)).map((r) => ({ ...r, device: r.device.toUpperCase() }))
}

// io_list에 없는 보조 릴레이(M 등)를 모은다. 타이머·카운터는 따로 보여 준다.
export function internalDevices(ir: Ir, io: IoRow[]): string[] {
  const known = new Set(io.map((r) => r.device.toUpperCase()))
  const out = new Set<string>()
  for (const rung of ir.rungs) {
    for (const o of rung.outputs) {
      const d = deviceOf(o.target, io)
      if (!known.has(d) && !isTimer(d) && !isCounter(d)) out.add(d)
    }
  }
  return [...out]
}

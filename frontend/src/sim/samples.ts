import type { Condition, Ir, IoRow } from './engine'

export type Sample = { key: string; title: string; io: IoRow[]; conditions: Condition[]; assumptions: string[]; ir: Ir }

const no = (signal: string) => ({ type: 'contact' as const, kind: 'NO' as const, signal })
const nc = (signal: string) => ({ type: 'contact' as const, kind: 'NC' as const, signal })

export const SAMPLES: Sample[] = [
  {
    key: 'self_hold',
    title: '자기유지 (START → 유지, STOP → 정지)',
    io: [
      { device: 'X1', name: 'START', kind: '푸시버튼 NO', desc: '시작 버튼' },
      { device: 'X2', name: 'STOP', kind: '푸시버튼 NC', desc: '정지 버튼(평상시 ON)' },
      { device: 'Y0', name: 'MOTOR', kind: '모터', desc: '컨베이어 모터' },
    ],
    conditions: [
      { id: 'C1', text: 'START를 누르면 MOTOR가 켜지고 손을 떼도 유지된다.' },
      { id: 'C2', text: 'STOP을 누르면 MOTOR가 꺼진다.' },
    ],
    assumptions: [],
    ir: {
      version: 1,
      rungs: [
        {
          id: 'R1', comment: '모터 자기유지', covers: ['C1', 'C2'],
          condition: { type: 'AND', items: [{ type: 'OR', items: [no('X1'), no('Y0')] }, no('X2')] },
          outputs: [{ kind: 'OUT', target: 'Y0' }],
        },
      ],
    },
  },
  {
    key: 'on_delay',
    title: '지연 후 켜짐 (START → 3초 뒤 MOTOR)',
    io: [
      { device: 'X1', name: 'START', kind: '푸시버튼 NO', desc: '시작 버튼' },
      { device: 'X2', name: 'STOP', kind: '푸시버튼 NC', desc: '정지 버튼(평상시 ON)' },
      { device: 'Y0', name: 'LAMP', kind: '램프', desc: '경고 램프' },
      { device: 'Y1', name: 'MOTOR', kind: '모터', desc: '컨베이어 모터' },
    ],
    conditions: [
      { id: 'C1', text: 'START를 누르면 LAMP가 켜진다.' },
      { id: 'C2', text: 'LAMP가 켜진 뒤 3초 후에 MOTOR가 켜진다.' },
      { id: 'C3', text: 'STOP을 누르면 모두 꺼진다.' },
    ],
    assumptions: ['START를 한 번 누르면 STOP 전까지 유지된다고 가정했어요.'],
    ir: {
      version: 1,
      rungs: [
        {
          id: 'R1', comment: '램프 자기유지', covers: ['C1', 'C3'],
          condition: { type: 'AND', items: [{ type: 'OR', items: [no('X1'), no('Y0')] }, no('X2')] },
          outputs: [{ kind: 'OUT', target: 'Y0' }],
        },
        { id: 'R2', comment: '3초 지연 타이머', covers: ['C2'], condition: no('Y0'), outputs: [{ kind: 'TON', target: 'T0', preset_ms: 3000 }] },
        { id: 'R3', comment: '지연 후 모터', covers: ['C2'], condition: no('T0'), outputs: [{ kind: 'OUT', target: 'Y1' }] },
      ],
    },
  },
  {
    key: 'estop',
    title: '비상정지 + 정/역 인터록',
    io: [
      { device: 'X0', name: 'EMG', kind: '푸시버튼 NC', desc: '비상정지(평상시 ON)' },
      { device: 'X1', name: 'START', kind: '푸시버튼 NO', desc: '시작' },
      { device: 'X2', name: 'STOP', kind: '푸시버튼 NC', desc: '정지(평상시 ON)' },
      { device: 'Y0', name: 'MOTOR_FWD', kind: '모터', desc: '정방향' },
      { device: 'Y1', name: 'MOTOR_REV', kind: '모터', desc: '역방향' },
    ],
    conditions: [
      { id: 'C1', text: 'START를 누르면 MOTOR_FWD가 켜지고 유지된다.' },
      { id: 'C2', text: 'MOTOR_FWD가 켜져 있으면 MOTOR_REV는 켜지지 않는다.' },
      { id: 'C3', text: '비상정지(X0) 입력 시 모든 출력이 OFF 된다.' },
    ],
    assumptions: ['비상정지 조건은 입력 설정에 따라 자동으로 추가했어요.'],
    ir: {
      version: 1,
      rungs: [
        {
          id: 'R1', comment: '정방향 자기유지 + 비상정지 + 역방향 인터록', covers: ['C1', 'C2', 'C3'],
          condition: { type: 'AND', items: [no('X0'), { type: 'OR', items: [no('X1'), no('Y0')] }, no('X2'), nc('Y1')] },
          outputs: [{ kind: 'OUT', target: 'Y0' }],
        },
      ],
    },
  },
]

/**
 * 시험 종류마다 화면이 쓰는 정의 — 표의 칸, 사내 규격 편집 칸, 시편 치수 칸, 미리 보기 값, 제품에서
 * 고를 수 있는 면 자리, 한 줄 요약. 표(`SpecimensPage`) · 편집 창(`PresetFieldsDialog`) · 시편 창
 * (`CouponDialog`) · 제품 적용 창(`ProductTestDialog`)이 이것을 읽는다 — 종류를 더하면 여기에 한
 * 벌 더한다.
 *
 * 굽힘은 칸이 많고 두께별 반지름 같은 규칙이 있어 따로 그린다(`PresetDialog` · `SpecimenDialog`).
 */

import type {
  AccelerationPreset,
  AnyPreset,
  CompressionPreset,
  CompressivePreset,
  CrushPreset,
  DirectedPreset,
  FaceSlot,
  FastenerPreset,
  ForcePreset,
  HandlePreset,
  LapPreset,
  ModalPreset,
  PressurePreset,
  ShearPreset,
  TensilePreset,
  TestKey,
  TorsionPreset,
  VibrationPreset,
} from '@/modules/specimens/api'

export type FieldGroup = 'specimen' | 'setup' | 'analysis'

/** 편집 · 치수 칸 하나 — 프리셋의 `group.key`. */
export interface Field {
  group: FieldGroup
  key: string
  label: string
  type?: 'number' | 'int' | 'bool' | 'select'
  /** 비워도 되는 칸 — 빈칸은 null 로 보낸다. */
  optional?: boolean
  options?: { value: string; label: string }[]
  /** 이 계열(도그본 · 띠 · 구멍 띠 …)에서만. */
  families?: string[]
}

/** 제품에서 고를 수 있는 면 자리. */
export interface Slot {
  slot: FaceSlot
  label: string
  /** 비웠을 때 쓰는 자리 — 없으면 꼭 골라야 한다. */
  fallback?: string
  /** 면 하나만. */
  single?: boolean
}

export interface Kind<P extends AnyPreset = AnyPreset> {
  test: P['test']
  label: string
  /** 표 위의 한 줄. */
  hint: string
  product: boolean
  columns: { head: string; text: (preset: P) => string }[]
  fields: Field[]
  summary: (preset: P) => string
  /** 시편 창이 보일 레시피 변수(서버가 푼 값) — 시편 시험만. */
  values?: { key: string; label: string }[]
  /** 제품 시험이 고를 수 있는 면 자리. */
  slots?: (preset: P) => Slot[]
}

const mm = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${value}`)
const size = (one: { length: number; width: number; thickness: number }) => `${one.length} × ${one.width} × ${one.thickness}`
const largeDeflection: Field = { group: 'analysis', key: 'large_deflection', label: '대변형 해석', type: 'bool' }
const support = (fallback = '아랫면'): Slot => ({ slot: 'support', label: '고정 면', fallback })

/** 종류의 정의를 합친 타입으로 — 표가 종류를 가린 뒤에만 부르므로 안전하다. */
function kind<P extends AnyPreset>(spec: Kind<P>): Kind {
  return spec as unknown as Kind
}

const TENSILE_FAMILY: Record<TensilePreset['family'], string> = { dogbone: '도그본', strip: '띠', open_hole: '구멍 띠' }
const DOGBONE = ['dogbone']

const TENSILE = kind<TensilePreset>({
  test: 'tensile',
  label: '인장',
  hint: '도그본 · 띠 · 구멍 띠 시편과 그립이 무는 자리, 해석 조건(한쪽 그립 고정, 다른 쪽 당김)이 포함된 작업을 생성합니다.',
  product: false,
  columns: [
    { head: '방식', text: (p) => TENSILE_FAMILY[p.family] },
    { head: '시편 (mm)', text: (p) => size(p.specimen) },
    {
      head: '평행부 · 구멍',
      text: (p) =>
        p.family === 'dogbone'
          ? `폭 ${mm(p.specimen.gauge_width)} · 길이 ${mm(p.specimen.parallel_length)} · R${mm(p.specimen.radius)}`
          : p.family === 'open_hole'
            ? `구멍 Ø${mm(p.specimen.hole_diameter)}`
            : '—',
    },
    { head: '표점 / 그립', text: (p) => `${p.specimen.gauge_length} / ${p.specimen.grip_length}` },
  ],
  fields: [
    { group: 'specimen', key: 'length', label: '전체 길이 (mm)' },
    { group: 'specimen', key: 'width', label: '그립부 폭 (mm)' },
    { group: 'specimen', key: 'thickness', label: '두께 (mm)' },
    { group: 'specimen', key: 'gauge_width', label: '평행부 폭 (mm)', families: DOGBONE },
    { group: 'specimen', key: 'parallel_length', label: '평행부 길이 (mm)', families: DOGBONE },
    { group: 'specimen', key: 'radius', label: '전이 반지름 (mm)', families: DOGBONE },
    { group: 'specimen', key: 'hole_diameter', label: '구멍 지름 (mm)', families: ['open_hole'] },
    { group: 'specimen', key: 'gauge_length', label: '표점 거리 (mm)' },
    { group: 'specimen', key: 'grip_length', label: '그립 길이 (mm)' },
    { group: 'analysis', key: 'strain', label: '공칭 변형률' },
    largeDeflection,
  ],
  values: [
    { key: '전이_길이', label: '전이부 길이' },
    { key: '그립_간격', label: '그립 간격' },
    { key: '늘림', label: '당김' },
  ],
  summary: (p) => `${TENSILE_FAMILY[p.family]} 시편의 한쪽 그립을 고정하고 다른 쪽을 그립 간격의 ${p.analysis.strain}배만큼 당깁니다.`,
})

const COMPRESSIVE_FAMILY: Record<CompressivePreset['family'], string> = { prism: '각기둥', cylinder: '원기둥', strip: '띠', open_hole: '구멍 띠' }
const GRIPPED = ['strip', 'open_hole']

const COMPRESSIVE = kind<CompressivePreset>({
  test: 'compressive',
  label: '압축',
  hint: '각기둥 · 원기둥은 세워서 위아래 가압면으로, 띠 · 구멍 띠는 양 끝 그립으로 누르는 작업을 생성합니다. 좌굴은 정적 해석으로 보이지 않습니다.',
  product: false,
  columns: [
    { head: '방식', text: (p) => COMPRESSIVE_FAMILY[p.family] },
    {
      head: '시편 (mm)',
      text: (p) => (p.family === 'cylinder' ? `Ø${p.specimen.width} × ${p.specimen.length}` : `${p.specimen.length} × ${p.specimen.width} × ${mm(p.specimen.thickness)}`),
    },
    { head: '그립 · 구멍', text: (p) => [p.specimen.grip_length ? `그립 ${p.specimen.grip_length}` : '', p.specimen.hole_diameter ? `구멍 Ø${p.specimen.hole_diameter}` : ''].filter(Boolean).join(' · ') || '가압판' },
  ],
  fields: [
    { group: 'specimen', key: 'length', label: '길이 (mm)' },
    { group: 'specimen', key: 'width', label: '폭 · 지름 (mm)' },
    { group: 'specimen', key: 'thickness', label: '두께 (mm)', families: ['prism', ...GRIPPED] },
    { group: 'specimen', key: 'grip_length', label: '그립 길이 (mm)', families: GRIPPED },
    { group: 'specimen', key: 'hole_diameter', label: '구멍 지름 (mm)', families: ['open_hole'] },
    { group: 'analysis', key: 'strain', label: '공칭 변형률' },
    largeDeflection,
  ],
  values: [
    { key: '자유_길이', label: '자유 길이' },
    { key: '누름', label: '누름' },
  ],
  summary: (p) => `${COMPRESSIVE_FAMILY[p.family]} 시편을 공칭 변형률 ${p.analysis.strain}만큼 누릅니다.`,
})

const SHEAR = kind<ShearPreset>({
  test: 'shear',
  label: '전단',
  hint: 'V 노치 시편과 노치 양쪽의 물림 자리, 해석 조건(한쪽 고정, 다른 쪽을 폭 방향으로 이동)이 포함된 작업을 생성합니다.',
  product: false,
  columns: [
    { head: '시편 (mm)', text: (p) => size(p.specimen) },
    { head: '노치 (깊이 · 각 · R)', text: (p) => `${p.specimen.notch_depth} · ${p.specimen.notch_angle}° · R${p.specimen.notch_radius}` },
    { head: '물림 간격', text: (p) => `${p.specimen.grip_gap}` },
  ],
  fields: [
    { group: 'specimen', key: 'length', label: '길이 (mm)' },
    { group: 'specimen', key: 'width', label: '폭 (mm)' },
    { group: 'specimen', key: 'thickness', label: '두께 (mm)' },
    { group: 'specimen', key: 'notch_depth', label: '노치 깊이 (mm)' },
    { group: 'specimen', key: 'notch_angle', label: '노치 각 (°)' },
    { group: 'specimen', key: 'notch_radius', label: '노치 뿌리 반지름 (mm)' },
    { group: 'specimen', key: 'grip_gap', label: '물림 간격 (mm)' },
    { group: 'analysis', key: 'shear_strain', label: '전단 변형률' },
  ],
  values: [
    { key: '노치_입구', label: '노치 입구 반폭' },
    { key: '전단_변위', label: '가압 변위' },
  ],
  summary: (p) => `노치 양쪽 반을 물어 한쪽을 고정하고 다른 쪽을 폭 방향으로 물림 간격의 ${p.analysis.shear_strain}배만큼 옮깁니다.`,
})

const LAP = kind<LapPreset>({
  test: 'lap',
  label: '접착 이음',
  hint: '피착재 둘과 접착층(본드 접촉), 그립이 무는 자리, 해석 조건이 포함된 작업을 생성합니다. 피착재와 접착층의 물성을 각각 지정하십시오.',
  product: false,
  columns: [
    { head: '피착재 (mm)', text: (p) => size(p.specimen) },
    { head: '겹침 / 접착층', text: (p) => `${p.specimen.overlap} / ${p.specimen.bondline}` },
    { head: '그립', text: (p) => `${p.specimen.grip_length}` },
  ],
  fields: [
    { group: 'specimen', key: 'length', label: '피착재 길이 (mm)' },
    { group: 'specimen', key: 'width', label: '폭 (mm)' },
    { group: 'specimen', key: 'thickness', label: '피착재 두께 (mm)' },
    { group: 'specimen', key: 'overlap', label: '겹침 길이 (mm)' },
    { group: 'specimen', key: 'bondline', label: '접착층 두께 (mm)' },
    { group: 'specimen', key: 'grip_length', label: '그립 길이 (mm)' },
    { group: 'analysis', key: 'displacement', label: '당김 (mm)' },
    largeDeflection,
  ],
  values: [{ key: '당김', label: '당김' }],
  summary: (p) => `아래 피착재의 끝을 고정하고 위 피착재의 끝을 ${p.analysis.displacement} mm 당깁니다.`,
})

const FASTENER = kind<FastenerPreset>({
  test: 'fastener',
  label: '체결부',
  hint: '핀 베어링(강체 핀이 구멍 가장자리를 민다)과 체결구 뽑힘(판 둘레를 물고 체결구를 당긴다) 시편, 접촉 · 해석 조건이 포함된 작업을 생성합니다.',
  product: false,
  columns: [
    { head: '방식', text: (p) => (p.family === 'bearing' ? '핀 베어링' : '뽑힘') },
    { head: '판 (mm)', text: (p) => size(p.specimen) },
    {
      head: '구멍 · 체결구',
      text: (p) =>
        p.family === 'bearing'
          ? `Ø${p.specimen.hole_diameter} · 끝 거리 ${mm(p.specimen.edge_distance)}`
          : `Ø${p.specimen.hole_diameter} · 머리 Ø${mm(p.specimen.head_diameter)} · 받침 Ø${mm(p.specimen.support_diameter)}`,
    },
  ],
  fields: [
    { group: 'specimen', key: 'length', label: '길이 (mm)' },
    { group: 'specimen', key: 'width', label: '폭 (mm)' },
    { group: 'specimen', key: 'thickness', label: '두께 (mm)' },
    { group: 'specimen', key: 'hole_diameter', label: '구멍 지름 (mm)' },
    { group: 'specimen', key: 'edge_distance', label: '끝 거리 (mm)', families: ['bearing'] },
    { group: 'specimen', key: 'grip_length', label: '그립 길이 (mm)', families: ['bearing'] },
    { group: 'specimen', key: 'head_diameter', label: '머리 지름 (mm)', families: ['pull_through'] },
    { group: 'specimen', key: 'head_height', label: '머리 높이 (mm)', families: ['pull_through'] },
    { group: 'specimen', key: 'support_diameter', label: '받침 고리 안지름 (mm)', families: ['pull_through'] },
    { group: 'analysis', key: 'displacement', label: '이동 (mm)' },
    { group: 'analysis', key: 'friction', label: '마찰계수' },
    largeDeflection,
  ],
  values: [{ key: '당김', label: '이동' }],
  summary: (p) => (p.family === 'bearing' ? `강체 핀을 가까운 끝 쪽으로 ${p.analysis.displacement} mm 옮겨 구멍을 밉니다.` : `판 둘레를 물고 체결구를 ${p.analysis.displacement} mm 당깁니다.`),
})

const FORCE = kind<ForcePreset>({
  test: 'force',
  label: '정하중',
  hint: '제품의 아랫면을 고정하고 윗면(또는 3D에서 고른 면)을 원형 접촉면으로 누릅니다. 제품의 물성은 그대로 사용합니다.',
  product: true,
  columns: [
    { head: '하중 (N)', text: (p) => `${p.setup.force}` },
    { head: '접촉 지름 (mm)', text: (p) => `${p.setup.probe_diameter}` },
  ],
  fields: [{ group: 'setup', key: 'force', label: '하중 (N)' }, { group: 'setup', key: 'probe_diameter', label: '접촉 지름 (mm)' }, largeDeflection],
  slots: () => [{ slot: 'load', label: '누를 면', fallback: '윗면', single: true }, support()],
  summary: (p) => `지름 ${p.setup.probe_diameter} mm 원으로 ${p.setup.force} N 누르고 받침을 고정합니다.`,
})

const DIRECTED = kind<DirectedPreset>({
  test: 'directed',
  label: '방향 하중',
  hint: '3D에서 고른 면(코드 고정부, 커넥터 등)에 정한 방향의 힘과 그 축을 도는 모멘트를 겁니다. 방향을 비우면 고른 면에서 바깥으로 당깁니다.',
  product: true,
  columns: [
    { head: '힘 (N)', text: (p) => mm(p.setup.force) },
    { head: '모멘트 (N·m)', text: (p) => mm(p.setup.torque) },
  ],
  fields: [{ group: 'setup', key: 'force', label: '힘 (N)', optional: true }, { group: 'setup', key: 'torque', label: '모멘트 (N·m)', optional: true }, largeDeflection],
  slots: () => [{ slot: 'load', label: '하중 면' }, support()],
  summary: (p) => `고른 면에 ${[p.setup.force ? `힘 ${p.setup.force} N` : '', p.setup.torque ? `모멘트 ${p.setup.torque} N·m` : ''].filter(Boolean).join(' · ')}를 겁니다.`,
})

const CRUSH = kind<CrushPreset>({
  test: 'crush',
  label: '압착',
  hint: '평판 둘 사이에서 누릅니다. 기본은 윗면 전체를 누르고 아랫면을 받치며, 3D에서 누를 면을 고르면 그 반대쪽 끝 면이 받침입니다.',
  product: true,
  columns: [{ head: '힘 (N)', text: (p) => `${p.setup.force}` }],
  fields: [{ group: 'setup', key: 'force', label: '힘 (N)' }, largeDeflection],
  slots: () => [{ slot: 'load', label: '누를 면', fallback: '윗면 전체' }, support('반대쪽 끝 면')],
  summary: (p) => `평판으로 ${p.setup.force} N 누릅니다.`,
})

const PRESSURE = kind<PressurePreset>({
  test: 'pressure',
  label: '수압',
  hint: '물 깊이만큼의 수압을 바깥 면에 고르게 겁니다. 속이 빈 제품이나 조립은 바깥 면만 3D에서 고르십시오. 받침은 강체 운동만 막습니다.',
  product: true,
  columns: [
    { head: '수심 (m)', text: (p) => `${p.setup.depth}` },
    { head: '수압 (kPa)', text: (p) => `${Math.round(p.setup.depth * p.setup.factor * 9.80665 * 100) / 100}` },
    { head: '계수', text: (p) => `${p.setup.factor}` },
  ],
  fields: [{ group: 'setup', key: 'depth', label: '수심 (m)' }, { group: 'setup', key: 'factor', label: '계수' }, largeDeflection],
  slots: () => [{ slot: 'load', label: '수압 면', fallback: '모든 면' }, support()],
  summary: (p) => `수심 ${p.setup.depth} m의 수압을 바깥 면에 겁니다.`,
})

const ACCELERATION = kind<AccelerationPreset>({
  test: 'acceleration',
  label: '등가 가속도',
  hint: '충격 · 운송 가속도를 정적 가속도(g × 배율)로 근사합니다. 받침을 고정하고 한 축으로 가속합니다. 실제 충격 응답은 고유진동수에 따라 다릅니다.',
  product: true,
  columns: [
    { head: '가속도 (g)', text: (p) => `${p.setup.acceleration_g}` },
    { head: '지속 (ms)', text: (p) => mm(p.setup.duration_ms) },
    { head: '배율', text: (p) => `${p.setup.factor}` },
  ],
  fields: [
    { group: 'setup', key: 'acceleration_g', label: '가속도 (g)' },
    { group: 'setup', key: 'duration_ms', label: '지속 시간 (ms)', optional: true },
    { group: 'setup', key: 'factor', label: '응답 배율' },
    largeDeflection,
  ],
  slots: () => [support()],
  summary: (p) => `받침을 고정하고 한 축으로 ${p.setup.acceleration_g * p.setup.factor} g를 정적으로 겁니다.`,
})

const HANDLE = kind<HandlePreset>({
  test: 'handle',
  label: '손잡이·벽걸이',
  hint: '3D에서 고른 자리(손잡이를 잡는 면, 벽걸이 브래킷이 닿는 면)를 고정하고 제품 무게의 배수가 아래(-Z)로 걸리게 합니다. 물성의 밀도가 무게를 정합니다.',
  product: true,
  columns: [{ head: '무게 배수', text: (p) => `${p.setup.weight_factor}배` }],
  fields: [{ group: 'setup', key: 'weight_factor', label: '무게 배수' }, largeDeflection],
  slots: () => [{ slot: 'support', label: '고정 자리' }],
  summary: (p) => `고른 자리를 고정하고 무게의 ${p.setup.weight_factor}배가 아래로 걸리게 합니다.`,
})

const COMPRESSION = kind<CompressionPreset>({
  test: 'compression',
  label: '적층 압축',
  hint: '아랫면을 받치고 윗면 전체를 위에 쌓인 무게로 누릅니다. 제품 무게(kg)는 적용할 때 입력합니다.',
  product: true,
  columns: [
    { head: '적재', text: (p) => (p.setup.layers ? `${p.setup.layers}단` : `높이 ${p.setup.stack_height} mm`) },
    { head: '계수', text: (p) => `${p.setup.factor}` },
  ],
  fields: [
    { group: 'setup', key: 'layers', label: '적재 단수', type: 'int', optional: true },
    { group: 'setup', key: 'stack_height', label: '적재 높이 (mm)', optional: true },
    { group: 'setup', key: 'factor', label: '계수' },
    largeDeflection,
  ],
  summary: (p) =>
    p.setup.layers
      ? `무게 × g × (${p.setup.layers} − 1) × ${p.setup.factor}로 윗면 전체를 누릅니다.`
      : `무게 × g × (${p.setup.stack_height} − 제품 높이) / 제품 높이 × ${p.setup.factor}로 윗면 전체를 누릅니다.`,
})

const TORSION = kind<TorsionPreset>({
  test: 'torsion',
  label: '비틀림',
  hint: '긴 축의 한쪽 끝을 고정하고 다른 끝을 그 축으로 돌립니다. 끝이 둥근 제품은 끝 면을 3D에서 고르십시오.',
  product: true,
  columns: [{ head: '각도 (°)', text: (p) => `${p.setup.angle}` }],
  fields: [{ group: 'setup', key: 'angle', label: '비트는 각 (°)' }, largeDeflection],
  slots: () => [
    { slot: 'support', label: '고정 끝', fallback: '긴 축의 앞 끝' },
    { slot: 'twist', label: '비트는 끝', fallback: '긴 축의 뒤 끝' },
  ],
  summary: (p) => `한쪽 끝을 고정하고 다른 끝을 ${p.setup.angle}° 비틉니다.`,
})

const VIBRATION = kind<VibrationPreset>({
  test: 'vibration',
  label: '진동',
  hint: '제품의 아랫면(또는 고른 면)을 가진대에 고정하고 한 축으로 정현파 가속도를 주어 주파수를 훑습니다(조화 응답).',
  product: true,
  columns: [
    { head: '주파수 (Hz)', text: (p) => `${p.setup.freq_min}~${p.setup.freq_max}` },
    { head: '가속도 (g)', text: (p) => `${p.setup.acceleration_g}` },
    { head: '감쇠비', text: (p) => `${p.setup.damping_ratio}` },
  ],
  fields: [
    { group: 'setup', key: 'freq_min', label: '최소 주파수 (Hz)' },
    { group: 'setup', key: 'freq_max', label: '최대 주파수 (Hz)' },
    { group: 'setup', key: 'acceleration_g', label: '가속도 (g)' },
    { group: 'setup', key: 'damping_ratio', label: '감쇠비' },
    { group: 'setup', key: 'modes', label: '모드 수', type: 'int' },
    { group: 'setup', key: 'points', label: '주파수 점 수', type: 'int' },
  ],
  slots: () => [support()],
  summary: (p) => `받침을 고정하고 한 축으로 ${p.setup.acceleration_g} g를 ${p.setup.freq_min}~${p.setup.freq_max} Hz에서 가진합니다(감쇠비 ${p.setup.damping_ratio}).`,
})

const MODAL = kind<ModalPreset>({
  test: 'modal',
  label: '고유진동수',
  hint: '시험 주파수 범위 안의 고유진동수를 구합니다(공진 탐색). 받침을 고정하거나 구속 없이(자유-자유) 둡니다.',
  product: true,
  columns: [
    { head: '주파수 (Hz)', text: (p) => (p.setup.freq_max ? `${p.setup.freq_min}~${p.setup.freq_max}` : '—') },
    { head: '모드 수', text: (p) => `${p.setup.modes}` },
    { head: '받침', text: (p) => (p.setup.support === 'free' ? '자유-자유' : '고정') },
  ],
  fields: [
    { group: 'setup', key: 'modes', label: '모드 수', type: 'int' },
    { group: 'setup', key: 'freq_min', label: '최소 주파수 (Hz)' },
    { group: 'setup', key: 'freq_max', label: '최대 주파수 (Hz)', optional: true },
    {
      group: 'setup',
      key: 'support',
      label: '받침',
      type: 'select',
      options: [
        { value: 'fixed', label: '고정' },
        { value: 'free', label: '자유-자유' },
      ],
    },
  ],
  slots: (p) => (p.setup.support === 'fixed' ? [support()] : []),
  summary: (p) =>
    p.setup.support === 'free'
      ? `구속 없이 모드 ${p.setup.modes}개(강체 모드 제외)를 구합니다.`
      : `받침을 고정하고 ${p.setup.freq_max ? `${p.setup.freq_min}~${p.setup.freq_max} Hz 안의 ` : ''}모드를 최대 ${p.setup.modes}개 구합니다.`,
})

/** 굽힘을 뺀 종류 — 표에 보이는 순서. */
export const KINDS: Kind[] = [TENSILE, COMPRESSIVE, SHEAR, LAP, FASTENER, FORCE, DIRECTED, HANDLE, CRUSH, COMPRESSION, PRESSURE, TORSION, ACCELERATION, VIBRATION, MODAL]

export function kindOf(test: TestKey): Kind | undefined {
  return KINDS.find((one) => one.test === test)
}

/** 이 프리셋의 계열에 맞는 칸 — 도그본 칸은 띠에서 뺀다. */
export function fieldsFor(spec: Kind, preset: AnyPreset): Field[] {
  const family = 'family' in preset ? preset.family : ''
  return spec.fields.filter((one) => !one.families || one.families.includes(family))
}

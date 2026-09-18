/**
 * 레시피 편집기가 아는 피처 종류와 칸 — **서버 `core/recipe/schema.py` 와 짝.**
 *
 * 서버가 JSON Schema 를 주지만(`/cad/recipe/schema`) 폼의 말 · 순서 · 도움말은 사람이 정한다.
 * 연산을 더할 때 여기 한 항목과 서버의 피처 클래스를 함께 더한다 — `router.test` 처럼 어긋남을
 * 잡는 시험은 `recipeSpec.test.ts` 가 서버 스키마와 대조한다.
 */

import type { Recipe } from '@/modules/cad/api'

export type RecipeNode = Record<string, unknown> & { id: string; op: string; label?: string }

export type FieldKind =
  | 'number'
  | 'text'
  | 'select'
  | 'xy'
  | 'xyz'
  | 'ref'
  | 'refs'
  | 'points'
  | 'plane'
  | 'shapes'
  | 'checkbox'

export interface FieldSpec {
  key: string
  label: string
  kind: FieldKind
  options?: { value: string; label: string }[]
  step?: number
  help?: string
  /** 어떤 종류의 앞 피처를 가리키나 — ref/refs 에서 고를 목록을 좁힌다. */
  refKind?: 'sketch' | 'solid' | 'any'
}

export interface OpSpec {
  op: string
  label: string
  group: '스케치' | '입체' | '조합' | '마감' | '배치'
  help: string
  fields: FieldSpec[]
  /** 새 피처의 기본값. id · label 은 만들 때 붙인다. */
  defaults: Record<string, unknown>
}

const EDGE_OPTIONS = [
  { value: 'all', label: '전부' },
  { value: 'vertical', label: '수직 엣지' },
  { value: 'horizontal', label: '수평 엣지' },
  { value: 'top', label: '윗면 둘레' },
  { value: 'bottom', label: '바닥 둘레' },
]
const AXIS_OPTIONS = ['X', 'Y', 'Z'].map((a) => ({ value: a, label: a }))
export const PLANE_OPTIONS = ['XY', 'XZ', 'YZ', 'YX', 'ZX', 'ZY'].map((p) => ({ value: p, label: p }))

export const OP_SPECS: OpSpec[] = [
  {
    op: 'sketch',
    label: '스케치',
    group: '스케치',
    help: '평면 위의 2D 윤곽. 도형을 더하거나(add) 빼서(cut) 만든다.',
    fields: [
      { key: 'plane', label: '평면', kind: 'plane' },
      { key: 'shapes', label: '도형', kind: 'shapes' },
    ],
    defaults: { plane: { name: 'XY', origin: [0, 0, 0] }, shapes: [{ type: 'rect', width: 40, height: 30, at: [0, 0], rotation: 0, mode: 'add' }] },
  },
  {
    op: 'extrude',
    label: '돌출',
    group: '입체',
    help: '스케치를 평면 법선 방향으로 밀어 입체로.',
    fields: [
      { key: 'sketch', label: '스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'distance', label: '거리 (mm)', kind: 'number' },
      {
        key: 'direction',
        label: '방향',
        kind: 'select',
        options: [
          { value: 'normal', label: '법선 쪽' },
          { value: 'reverse', label: '반대' },
          { value: 'both', label: '양쪽' },
        ],
      },
    ],
    defaults: { sketch: '', distance: 10, direction: 'normal' },
  },
  {
    op: 'revolve',
    label: '회전',
    group: '입체',
    help: '스케치를 축 둘레로 돌려 입체로.',
    fields: [
      { key: 'sketch', label: '스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'angle', label: '각도 (°)', kind: 'number', step: 1 },
    ],
    defaults: { sketch: '', axis: 'Z', angle: 360 },
  },
  {
    op: 'box',
    label: '상자',
    group: '입체',
    help: '중심이 at 인 상자.',
    fields: [
      { key: 'length', label: '길이 X (mm)', kind: 'number' },
      { key: 'width', label: '너비 Y (mm)', kind: 'number' },
      { key: 'height', label: '높이 Z (mm)', kind: 'number' },
      { key: 'at', label: '중심', kind: 'xyz' },
    ],
    defaults: { length: 40, width: 30, height: 20, at: [0, 0, 0] },
  },
  {
    op: 'cylinder',
    label: '원기둥',
    group: '입체',
    help: '중심이 at 인 원기둥.',
    fields: [
      { key: 'radius', label: '반지름 (mm)', kind: 'number' },
      { key: 'height', label: '높이 (mm)', kind: 'number' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'at', label: '중심', kind: 'xyz' },
    ],
    defaults: { radius: 10, height: 20, axis: 'Z', at: [0, 0, 0] },
  },
  {
    op: 'union',
    label: '합치기',
    group: '조합',
    help: '여러 입체를 하나로.',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'solid' }],
    defaults: { targets: [] },
  },
  {
    op: 'cut',
    label: '빼기',
    group: '조합',
    help: '대상에서 도구를 뺀다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'tools', label: '도구', kind: 'refs', refKind: 'solid' },
    ],
    defaults: { target: '', tools: [] },
  },
  {
    op: 'intersect',
    label: '교집합',
    group: '조합',
    help: '겹치는 부분만 남긴다.',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'solid' }],
    defaults: { targets: [] },
  },
  {
    op: 'fillet',
    label: '필렛',
    group: '마감',
    help: '엣지를 둥글린다. 인접 면보다 작게.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'edges', label: '엣지', kind: 'select', options: EDGE_OPTIONS },
      { key: 'radius', label: '반지름 (mm)', kind: 'number' },
    ],
    defaults: { target: '', edges: 'vertical', radius: 2 },
  },
  {
    op: 'chamfer',
    label: '모따기',
    group: '마감',
    help: '엣지를 깎는다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'edges', label: '엣지', kind: 'select', options: EDGE_OPTIONS },
      { key: 'length', label: '길이 (mm)', kind: 'number' },
    ],
    defaults: { target: '', edges: 'all', length: 1 },
  },
  {
    op: 'hole',
    label: '구멍',
    group: '마감',
    help: '위(+Z)에서 아래로 뚫는다. 깊이를 비우면 관통.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'at', label: '위치들 (X, Y)', kind: 'points' },
      { key: 'diameter', label: '지름 (mm)', kind: 'number' },
      { key: 'depth', label: '깊이 (mm, 비우면 관통)', kind: 'number' },
    ],
    defaults: { target: '', at: [[0, 0]], diameter: 6, depth: null },
  },
  {
    op: 'pattern',
    label: '패턴',
    group: '배치',
    help: '피처를 여러 벌 복제한다. 결과는 묶음이라 빼기의 도구나 합치기의 대상으로 쓴다.',
    fields: [
      { key: 'source', label: '원본', kind: 'ref', refKind: 'any' },
      {
        key: 'kind',
        label: '종류',
        kind: 'select',
        options: [
          { value: 'linear', label: '직선' },
          { value: 'circular', label: '원형' },
        ],
      },
      { key: 'count', label: '개수', kind: 'number', step: 1 },
      { key: 'spacing', label: '간격 (직선)', kind: 'xyz' },
      { key: 'axis', label: '축 (원형)', kind: 'select', options: AXIS_OPTIONS },
      { key: 'angle', label: '전체 각도 (원형)', kind: 'number', step: 1 },
    ],
    defaults: { source: '', kind: 'linear', count: 4, spacing: [10, 0, 0], axis: 'Z', angle: 360 },
  },
  {
    op: 'transform',
    label: '이동 · 회전',
    group: '배치',
    help: '회전한 뒤 이동한다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'any' },
      { key: 'translate', label: '이동', kind: 'xyz' },
      { key: 'rotate', label: '회전 (°)', kind: 'xyz' },
    ],
    defaults: { target: '', translate: [0, 0, 0], rotate: [0, 0, 0] },
  },
  {
    op: 'mirror',
    label: '거울',
    group: '배치',
    help: '평면에 비춘다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'any' },
      { key: 'plane', label: '거울 평면', kind: 'select', options: PLANE_OPTIONS },
      { key: 'keep_original', label: '원본도 남긴다', kind: 'checkbox' },
    ],
    defaults: { target: '', plane: 'YZ', keep_original: true },
  },
  {
    op: 'import_step',
    label: 'STEP 가져오기',
    group: '입체',
    help: '올린 STEP(작업물 id). 「STEP 올리기」 가 만든다 — 직접 넣지 않는다.',
    fields: [{ key: 'file', label: '작업물 id', kind: 'text' }],
    defaults: { file: '' },
  },
]

export const OP_BY_NAME: Record<string, OpSpec> = Object.fromEntries(OP_SPECS.map((s) => [s.op, s]))

export const SHAPE_TYPES = [
  { value: 'rect', label: '사각형' },
  { value: 'circle', label: '원' },
  { value: 'slot', label: '슬롯' },
  { value: 'regular_polygon', label: '정다각형' },
  { value: 'polygon', label: '다각형' },
]

export function defaultShape(type: string): Record<string, unknown> {
  const base = { at: [0, 0], rotation: 0, mode: 'add' }
  switch (type) {
    case 'circle':
      return { type, radius: 5, ...base }
    case 'slot':
      return { type, length: 20, width: 6, ...base }
    case 'regular_polygon':
      return { type, radius: 10, sides: 6, ...base }
    case 'polygon':
      return { type, points: [[-10, -10], [10, -10], [0, 10]], ...base }
    default:
      return { type: 'rect', width: 20, height: 10, ...base }
  }
}

/** 새 피처 id — `<op>-<n>`, 안 겹치게. */
export function newNodeId(op: string, nodes: RecipeNode[]): string {
  const taken = new Set(nodes.map((n) => n.id))
  for (let n = 1; ; n += 1) {
    const candidate = `${op}-${n}`
    if (!taken.has(candidate)) return candidate
  }
}

export function makeNode(op: string, nodes: RecipeNode[]): RecipeNode {
  const spec = OP_BY_NAME[op]
  return { id: newNodeId(op, nodes), op, label: '', ...structuredClone(spec.defaults) }
}

/** 이 피처가 만드는 것이 스케치인가 입체인가 — ref 목록을 좁힐 때 쓴다. */
export function nodeKind(node: RecipeNode, nodes: RecipeNode[]): 'sketch' | 'solid' {
  if (node.op === 'sketch') return 'sketch'
  if (node.op === 'pattern' || node.op === 'transform' || node.op === 'mirror') {
    const source = nodes.find((n) => n.id === (node.source ?? node.target))
    return source ? nodeKind(source, nodes) : 'solid'
  }
  return 'solid'
}

/** 피처가 가리키는 앞 피처 id 들. */
export function referencesOf(node: RecipeNode): string[] {
  const out: string[] = []
  for (const key of ['sketch', 'target', 'source']) {
    const value = node[key]
    if (typeof value === 'string' && value) out.push(value)
  }
  for (const key of ['targets', 'tools']) {
    const value = node[key]
    if (Array.isArray(value)) out.push(...(value as string[]))
  }
  return out
}

export function nodesOf(recipe: Recipe): RecipeNode[] {
  return recipe.nodes as RecipeNode[]
}

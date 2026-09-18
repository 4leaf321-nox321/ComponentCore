/**
 * 레시피 편집기가 아는 피처 종류와 칸 — **서버 `core/recipe/schema.py` 와 짝.**
 *
 * 서버가 JSON Schema 를 주지만(`/cad/recipe/schema`) 폼의 말 · 순서 · 도움말은 사람이 정한다.
 * 연산을 더할 때 여기 한 항목과 서버의 피처 클래스를 함께 더한다 — `router.test` 처럼 어긋남을
 * 잡는 시험은 `recipeSpec.test.ts` 가 서버 스키마와 대조한다.
 */

import {
  ArrowUpFromLine,
  Box,
  Circle,
  CircleDot,
  Combine,
  Cone,
  Cylinder,
  Diamond,
  FlipHorizontal,
  Grid3x3,
  Import,
  Layers,
  Expand,
  Route,
  Scan,
  Spline,
  Triangle,
  Waves,
  Fence,
  SquareSplitHorizontal,
  Move3d,
  Package,
  PenTool,
  Radius,
  RotateCw,
  Scissors,
  Shapes,
  Torus,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { Recipe } from '@/modules/cad/api'

export type RecipeNode = Record<string, unknown> & {
  id: string
  op: string
  label?: string
}

export type FieldKind =
  | 'align2'
  | 'align3'
  | 'number'
  | 'text'
  | 'select'
  | 'xy'
  | 'xyz'
  | 'ref'
  | 'refs'
  | 'points'
  | 'points3'
  | 'plane'
  | 'shapes'
  | 'checkbox'
  | 'faceselect'
  | 'holeplane'

export interface FieldSpec {
  key: string
  label: string
  kind: FieldKind
  options?: { value: string; label: string }[]
  step?: number
  help?: string
  /** 어떤 종류의 앞 피처를 가리키나 — ref/refs 에서 고를 목록을 좁힌다. */
  refKind?: 'sketch' | 'solid' | 'any'
  /** 비워도 되는 ref — 비우면 null 로 보낸다. */
  optional?: boolean
}

export interface OpSpec {
  op: string
  label: string
  group: '스케치' | '입체' | '조합' | '마감' | '배치'
  /** 툴바에 보일 짧은 이름. 없으면 label. */
  short?: string
  icon: LucideIcon
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
export const PLANE_OPTIONS = ['XY', 'XZ', 'YZ', 'YX', 'ZX', 'ZY'].map((p) => ({
  value: p,
  label: p,
}))

export const OP_SPECS: OpSpec[] = [
  {
    op: 'sketch',
    icon: PenTool,
    label: '스케치',
    group: '스케치',
    help: '평면 위의 2D 윤곽. 도형을 더하거나(add) 빼서(cut) 만든다.',
    fields: [
      { key: 'plane', label: '평면', kind: 'plane' },
      { key: 'shapes', label: '도형', kind: 'shapes' },
      { key: 'hull', label: '도형들을 감싸는 볼록 윤곽으로', kind: 'checkbox' },
      { key: 'offset', label: '윤곽 여유 (mm, 0 = 없음, 음수면 안쪽)', kind: 'number', step: 0.1 },
    ],
    defaults: {
      plane: { name: 'XY', origin: [0, 0, 0] },
      shapes: [
        {
          type: 'rect',
          width: 40,
          height: 30,
          at: [0, 0],
          rotation: 0,
          mode: 'add',
        },
      ],
    },
  },
  {
    op: 'extrude',
    icon: ArrowUpFromLine,
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
      { key: 'taper', label: '구배 (°, 양수면 갈수록 좁게)', kind: 'number', step: 1 },
      {
        key: 'until',
        label: '어디까지',
        kind: 'select',
        options: [
          { value: 'distance', label: '거리만큼' },
          { value: 'next', label: '대상의 다음 면까지' },
          { value: 'last', label: '대상의 마지막 면까지 (관통)' },
        ],
      },
      { key: 'target', label: '부딪힐 대상 (면까지일 때)', kind: 'ref', refKind: 'solid', optional: true },
    ],
    defaults: { sketch: '', distance: 10, direction: 'normal', taper: 0, until: 'distance', target: null },
  },
  {
    op: 'sweep',
    icon: Route,
    label: '스윕',
    group: '입체',
    help: '스케치(단면)를 경로를 따라 밀어 입체로 — 파이프 · 손잡이 · 홈. 스케치 평면의 원점이 경로 첫 점에 오게 두세요.',
    fields: [
      { key: 'sketch', label: '단면 스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'path', label: '경로 점 (X, Y, Z)', kind: 'points3' },
      { key: 'smooth', label: '매끄러운 곡선으로 잇기', kind: 'checkbox' },
    ],
    defaults: {
      sketch: '',
      path: [
        [0, 0, 0],
        [0, 0, 30],
        [30, 0, 60],
      ],
      smooth: false,
    },
  },
  {
    op: 'sheet_metal',
    icon: Fence,
    label: '판금',
    group: '입체',
    help: '옆에서 본 꺾은선을 따라 판을 접는다 — 브래킷 · ㄱ자 앵글 · 덮개. 「2t 판, 30 올라가 20 꺾임, 폭 40, 굽힘 R4」.',
    fields: [
      { key: 'thickness', label: '판 두께 (mm)', kind: 'number', step: 0.5 },
      { key: 'width', label: '폭 (mm, 미는 길이)', kind: 'number' },
      { key: 'path', label: '꺾은선 (평면 위 X, Y)', kind: 'points' },
      { key: 'plane', label: '꺾은선 평면', kind: 'plane' },
      { key: 'bend_radius', label: '굽힘 반지름 (mm, 0 = 각지게)', kind: 'number', step: 0.5 },
      {
        key: 'side',
        label: '두께가 붙는 쪽',
        kind: 'select',
        options: [
          { value: 'left', label: '꺾은선이 안쪽' },
          { value: 'right', label: '꺾은선이 바깥쪽' },
        ],
      },
    ],
    defaults: {
      thickness: 2,
      width: 40,
      path: [
        [0, 0],
        [0, 30],
        [20, 30],
      ],
      plane: { name: 'XZ', origin: [0, 0, 0] },
      bend_radius: 3,
      side: 'left',
    },
  },
  {
    op: 'helix',
    icon: Spline,
    label: '나선',
    group: '입체',
    help: '단면 스케치를 나선을 따라 밀어 — 스프링 · 나사산. 단면은 XY 원점에 그리면 시작점에 알맞게 놓인다. 단면이 피치보다 작아야 겹치지 않는다.',
    fields: [
      { key: 'sketch', label: '단면 스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'radius', label: '나선 반지름 (mm)', kind: 'number' },
      { key: 'pitch', label: '피치 (mm, 한 바퀴에 오르는 높이)', kind: 'number' },
      { key: 'height', label: '높이 (mm)', kind: 'number' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'at', label: '축 밑점', kind: 'xyz' },
      { key: 'lefthand', label: '왼나사(반대 방향)', kind: 'checkbox' },
    ],
    defaults: { sketch: '', radius: 10, pitch: 5, height: 30, axis: 'Z', at: [0, 0, 0], lefthand: false },
  },
  {
    op: 'revolve',
    icon: RotateCw,
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
    icon: Box,
    label: '블록',
    group: '입체',
    help: '중심이 at 인 직육면체(블록).',
    fields: [
      { key: 'length', label: '길이 X (mm)', kind: 'number' },
      { key: 'width', label: '너비 Y (mm)', kind: 'number' },
      { key: 'height', label: '높이 Z (mm)', kind: 'number' },
      { key: 'at', label: '기준 자리', kind: 'xyz' },
      { key: 'align', label: '기준 (치수를 어디에 맞추나)', kind: 'align3' },
    ],
    defaults: { length: 40, width: 30, height: 20, at: [0, 0, 0], align: ['center', 'center', 'center'] },
  },
  {
    op: 'wedge',
    icon: Triangle,
    label: '쐐기',
    group: '입체',
    help: '경사 블록 — 밑면은 길이·너비, 윗면은 좁아진다. 지그의 경사 받침 · 고임.',
    fields: [
      { key: 'length', label: '길이 X (mm)', kind: 'number' },
      { key: 'width', label: '너비 Y (mm)', kind: 'number' },
      { key: 'height', label: '높이 Z (mm)', kind: 'number' },
      { key: 'top_x_min', label: '윗면 X 시작 (mm)', kind: 'number' },
      { key: 'top_x_max', label: '윗면 X 끝 (비우면 안 줄임)', kind: 'number' },
      { key: 'top_z_min', label: '윗면 Z 시작 (mm)', kind: 'number' },
      { key: 'top_z_max', label: '윗면 Z 끝 (비우면 안 줄임)', kind: 'number' },
      { key: 'at', label: '기준 자리', kind: 'xyz' },
      { key: 'align', label: '기준', kind: 'align3' },
    ],
    defaults: {
      length: 40,
      width: 30,
      height: 20,
      top_x_min: 10,
      top_x_max: 30,
      top_z_min: 0,
      top_z_max: null,
      at: [0, 0, 0],
      align: ['center', 'center', 'center'],
    },
  },
  {
    op: 'cylinder',
    icon: Cylinder,
    label: '원통',
    group: '입체',
    help: '중심이 at 인 원통.',
    fields: [
      { key: 'radius', label: '반지름 (mm)', kind: 'number' },
      { key: 'height', label: '높이 (mm)', kind: 'number' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'at', label: '중심', kind: 'xyz' },
    ],
    defaults: { radius: 10, height: 20, axis: 'Z', at: [0, 0, 0] },
  },
  {
    op: 'sphere',
    icon: Circle,
    label: '구',
    group: '입체',
    help: '중심이 at 인 구.',
    fields: [
      { key: 'radius', label: '반지름 (mm)', kind: 'number' },
      { key: 'at', label: '중심', kind: 'xyz' },
    ],
    defaults: { radius: 10, at: [0, 0, 0] },
  },
  {
    op: 'cone',
    icon: Cone,
    label: '원뿔',
    group: '입체',
    help: '밑면 중심이 at. 윗반지름 0 이면 뾰족.',
    fields: [
      { key: 'bottom_radius', label: '밑 반지름 (mm)', kind: 'number' },
      { key: 'top_radius', label: '윗 반지름 (mm)', kind: 'number' },
      { key: 'height', label: '높이 (mm)', kind: 'number' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'at', label: '밑면 중심', kind: 'xyz' },
    ],
    defaults: {
      bottom_radius: 10,
      top_radius: 4,
      height: 20,
      axis: 'Z',
      at: [0, 0, 0],
    },
  },
  {
    op: 'torus',
    icon: Torus,
    label: '토러스',
    group: '입체',
    help: '도넛. 큰 반지름(중심선)과 작은 반지름(관 굵기).',
    fields: [
      { key: 'major_radius', label: '큰 반지름 (mm)', kind: 'number' },
      { key: 'minor_radius', label: '작은 반지름 (mm)', kind: 'number' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'at', label: '중심', kind: 'xyz' },
    ],
    defaults: { major_radius: 20, minor_radius: 4, axis: 'Z', at: [0, 0, 0] },
  },
  {
    op: 'loft',
    icon: Layers,
    label: '로프트',
    group: '입체',
    help: '두 개 이상의 스케치를 이어 입체로. 다른 높이의 평면에 스케치를 두고 순서대로 고른다.',
    fields: [
      {
        key: 'sketches',
        label: '스케치들 (순서대로)',
        kind: 'refs',
        refKind: 'sketch',
      },
      { key: 'ruled', label: '직선으로 잇기(각진 전이)', kind: 'checkbox' },
    ],
    defaults: { sketches: [], ruled: false },
  },
  {
    op: 'union',
    icon: Combine,
    label: '결합',
    group: '조합',
    help: '여러 입체를 하나로(합집합).',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'solid' }],
    defaults: { targets: [] },
  },
  {
    op: 'cut',
    icon: Scissors,
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
    icon: Shapes,
    label: '교차',
    group: '조합',
    help: '겹치는 부분만 남긴다(교집합).',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'solid' }],
    defaults: { targets: [] },
  },
  {
    op: 'fillet',
    icon: Radius,
    label: '블렌드',
    group: '마감',
    help: '엣지를 둥글린다(필렛 · 라운드). 반지름은 인접 면보다 작게.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'edges', label: '엣지', kind: 'select', options: EDGE_OPTIONS },
      { key: 'radius', label: '반지름 (mm)', kind: 'number' },
    ],
    defaults: { target: '', edges: 'vertical', radius: 2 },
  },
  {
    op: 'split',
    icon: SquareSplitHorizontal,
    label: '자르기',
    group: '조합',
    help: '평면으로 자른다 — 반쪽 지그 · 단면 보기. 「위」 는 평면 법선 쪽.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'plane', label: '자르는 평면', kind: 'plane' },
      {
        key: 'keep',
        label: '남길 쪽',
        kind: 'select',
        options: [
          { value: 'top', label: '위(법선 쪽)' },
          { value: 'bottom', label: '아래' },
          { value: 'both', label: '둘 다' },
        ],
      },
    ],
    defaults: { target: '', plane: { name: 'XY', origin: [0, 0, 0] }, keep: 'top' },
  },
  {
    op: 'section',
    icon: Scan,
    label: '단면',
    group: '스케치',
    help: '입체를 평면으로 자른 단면을 스케치로. 여유를 주고 돌출하면 그 높이의 포켓 윤곽이 된다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'plane', label: '자르는 평면', kind: 'plane' },
      { key: 'offset', label: '윤곽 여유 (mm)', kind: 'number', step: 0.1 },
    ],
    defaults: { target: '', plane: { name: 'XY', origin: [0, 0, 0] }, offset: 0 },
  },
  {
    op: 'chamfer',
    icon: Diamond,
    label: '챔퍼',
    group: '마감',
    help: '엣지를 비스듬히 깎는다(모따기).',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'edges', label: '엣지', kind: 'select', options: EDGE_OPTIONS },
      { key: 'length', label: '길이 (mm)', kind: 'number' },
    ],
    defaults: { target: '', edges: 'all', length: 1 },
  },
  {
    op: 'hole',
    icon: CircleDot,
    label: '구멍',
    group: '마감',
    help: '단순 · 카운터보어 · 카운터싱크 · 탭. 나사(M3~M12)를 고르면 치수를 표에서 채운다. 면을 안 주면 윗면(+Z)에서 아래로.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      {
        key: 'kind',
        label: '종류',
        kind: 'select',
        options: [
          { value: 'simple', label: '단순(관통/막힘)' },
          { value: 'counterbore', label: '카운터보어' },
          { value: 'countersink', label: '카운터싱크' },
          { value: 'tap', label: '탭(나사 구멍)' },
        ],
      },
      {
        key: 'thread',
        label: '나사 규격 (비우면 지름 직접)',
        kind: 'select',
        options: [
          { value: '__none__', label: '(직접 입력)' },
          ...['M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12'].map((m) => ({
            value: m,
            label: m,
          })),
        ],
      },
      {
        key: 'diameter',
        label: '지름 (mm, 나사를 고르면 비워도 됨)',
        kind: 'number',
      },
      { key: 'depth', label: '깊이 (mm, 비우면 관통)', kind: 'number' },
      { key: 'counter_diameter', label: '카운터 지름 (mm)', kind: 'number' },
      { key: 'counter_depth', label: '카운터보어 깊이 (mm)', kind: 'number' },
      {
        key: 'countersink_angle',
        label: '카운터싱크 각도 (°)',
        kind: 'number',
        step: 1,
      },
      { key: 'plane', label: '뚫는 면', kind: 'holeplane' },
      { key: 'at', label: '위치들 (면 위 X, Y)', kind: 'points' },
    ],
    defaults: {
      target: '',
      kind: 'simple',
      thread: null,
      diameter: 6,
      depth: null,
      counter_diameter: null,
      counter_depth: null,
      countersink_angle: 90,
      plane: null,
      at: [[0, 0]],
    },
  },
  {
    op: 'shell',
    icon: Package,
    label: '쉘',
    group: '마감',
    help: '속을 비운다. 뚫을 면을 고르면 그 면이 열리고 나머지가 껍질이 된다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'thickness', label: '두께 (mm)', kind: 'number' },
      { key: 'open', label: '뚫을 면', kind: 'faceselect' },
    ],
    defaults: { target: '', thickness: 2, open: 'top' },
  },
  {
    op: 'offset',
    icon: Expand,
    label: '여유',
    group: '마감',
    help: '전체를 두껍게(+) · 얇게(−). 제품 형상을 여유만큼 키워서 빼면 지그 포켓이 된다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'amount', label: '여유 (mm, 음수면 줄임)', kind: 'number', step: 0.1 },
      {
        key: 'corners',
        label: '모서리',
        kind: 'select',
        options: [
          { value: 'round', label: '둥글게' },
          { value: 'sharp', label: '뾰족하게' },
        ],
      },
    ],
    defaults: { target: '', amount: 0.5, corners: 'round' },
  },
  {
    op: 'draft',
    icon: Waves,
    label: '구배',
    group: '마감',
    help: '고른 면을 기울인다 — 기준 평면에 닿는 자리는 치수 그대로. 빼기 쉬운 포켓 · 금형.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      {
        key: 'faces',
        label: '면',
        kind: 'select',
        options: [
          { value: 'sides', label: '옆면 전부' },
          { value: 'top', label: '윗면' },
          { value: 'bottom', label: '바닥' },
          { value: 'all', label: '모든 면' },
        ],
      },
      { key: 'angle', label: '각도 (°)', kind: 'number', step: 0.5 },
      { key: 'neutral', label: '기준 평면 (치수가 그대로인 자리)', kind: 'plane' },
    ],
    defaults: { target: '', faces: 'sides', angle: 3, neutral: { name: 'XY', origin: [0, 0, 0] } },
  },
  {
    op: 'pattern',
    icon: Grid3x3,
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
          { value: 'grid', label: '격자' },
          { value: 'circular', label: '원형' },
        ],
      },
      { key: 'count', label: '개수 (격자: X 방향)', kind: 'number', step: 1 },
      { key: 'spacing', label: '간격 (직선 · 격자 X)', kind: 'xyz' },
      { key: 'count_y', label: '격자 Y 개수', kind: 'number', step: 1 },
      { key: 'spacing_y', label: '격자 Y 간격', kind: 'xyz' },
      {
        key: 'axis',
        label: '축 (원형)',
        kind: 'select',
        options: AXIS_OPTIONS,
      },
      { key: 'angle', label: '전체 각도 (원형)', kind: 'number', step: 1 },
    ],
    defaults: {
      source: '',
      kind: 'linear',
      count: 4,
      spacing: [10, 0, 0],
      count_y: 1,
      spacing_y: [0, 10, 0],
      axis: 'Z',
      angle: 360,
    },
  },
  {
    op: 'transform',
    icon: Move3d,
    label: '이동',
    group: '배치',
    help: '크기를 바꾸고(원점 기준) 회전한 뒤 이동한다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'any' },
      { key: 'translate', label: '이동', kind: 'xyz' },
      { key: 'rotate', label: '회전 (°)', kind: 'xyz' },
      { key: 'scale', label: '배율 (1 = 그대로)', kind: 'number', step: 0.1 },
    ],
    defaults: { target: '', translate: [0, 0, 0], rotate: [0, 0, 0], scale: 1 },
  },
  {
    op: 'mirror',
    icon: FlipHorizontal,
    label: '미러',
    group: '배치',
    help: '평면에 비춘다(대칭 복사).',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'any' },
      {
        key: 'plane',
        label: '대칭 평면',
        kind: 'select',
        options: PLANE_OPTIONS,
      },
      { key: 'keep_original', label: '원본도 남긴다', kind: 'checkbox' },
    ],
    defaults: { target: '', plane: 'YZ', keep_original: true },
  },
  {
    op: 'import_step',
    icon: Import,
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
  { value: 'polyline', label: '임의 윤곽' },
  { value: 'path', label: '선 (두께)' },
  { value: 'rounded_rect', label: '둥근 사각형' },
  { value: 'trapezoid', label: '사다리꼴' },
  { value: 'triangle', label: '삼각형 (변 · 각)' },
  { value: 'ellipse', label: '타원' },
  { value: 'text', label: '글자' },
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
      return {
        type,
        points: [
          [-10, -10],
          [10, -10],
          [0, 10],
        ],
        ...base,
      }
    case 'rounded_rect':
      return { type, width: 40, height: 30, radius: 5, ...base }
    case 'trapezoid':
      return { type, width: 40, height: 20, left_angle: 75, right_angle: null, ...base }
    case 'triangle':
      return { type, a: 30, b: 40, C: 90, ...base }
    case 'ellipse':
      return { type, x_radius: 15, y_radius: 8, ...base }
    case 'text':
      return { type, text: 'AJ', size: 8, bold: false, ...base }
    case 'path':
      return { type, start: [0, 0], segments: [{ to: [30, 0] }, { to: [30, 20] }], width: 3, corners: 'round', ...base }
    case 'polyline':
      return {
        type,
        start: [0, 0],
        segments: [{ to: [30, 0] }, { to: [30, 20], via: [36, 10] }, { to: [0, 20] }],
        ...base,
      }
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
  return {
    id: newNodeId(op, nodes),
    op,
    label: '',
    ...structuredClone(spec.defaults),
  }
}

/** 이 피처가 만드는 것이 스케치인가 입체인가 — ref 목록을 좁힐 때 쓴다. */
export function nodeKind(node: RecipeNode, nodes: RecipeNode[]): 'sketch' | 'solid' {
  if (node.op === 'sketch' || node.op === 'section') return 'sketch'
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
  for (const key of ['targets', 'tools', 'sketches']) {
    const value = node[key]
    if (Array.isArray(value)) out.push(...(value as string[]))
  }
  return out
}

export function nodesOf(recipe: Recipe): RecipeNode[] {
  return recipe.nodes as RecipeNode[]
}

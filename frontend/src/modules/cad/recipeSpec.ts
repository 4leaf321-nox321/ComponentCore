/**
 * 레시피 편집기가 아는 피처 종류와 칸 — **서버 `core/recipe/schema.py` 와 짝.**
 *
 * 서버가 JSON Schema 를 주지만(`/cad/recipe/schema`) 폼의 말 · 순서 · 도움말은 사람이 정한다.
 * 연산을 더할 때 여기 한 항목과 서버의 피처 클래스를 함께 더한다 — `router.test` 처럼 어긋남을
 * 잡는 시험은 `recipeSpec.test.ts` 가 서버 스키마와 대조한다.
 */

import {
  ArrowUpFromLine,
  Axis3d,
  Bolt,
  Box,
  Cog,
  CornerDownRight,
  Disc,
  Hexagon,
  Paperclip,
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
  Eraser,
  Expand,
  Route,
  Scan,
  Group,
  PackagePlus,
  Spline,
  Triangle,
  Wrench,
  Waves,
  Fence,
  Frame,
  Stamp,
  SquareDashed,
  FoldHorizontal,
  SquareDashedBottom,
  SquareSplitHorizontal,
  Move3d,
  Package,
  PenTool,
  Radius,
  RotateCw,
  Scissors,
  Shapes,
  Torus,
  Tornado,
  UnfoldHorizontal,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { Recipe } from '@/modules/cad/api'
import { defaultConstrained } from '@/modules/cad/ConstrainedSketch'

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
  | 'bends'
  | 'bendgroups'
  | 'axisref'
  | 'planeref'
  | 'datumaxis'
  | 'datumplane'
  | 'facepicks'
  | 'profile'
  | 'paths'
  | 'query'
  | 'json'

export interface FieldSpec {
  key: string
  label: string
  kind: FieldKind
  options?: { value: string; label: string }[]
  step?: number
  help?: string
  /** 어떤 종류의 앞 피처를 가리키나 — ref/refs 에서 고를 목록을 좁힌다. */
  refKind?: 'sketch' | 'solid' | 'any' | 'axis' | 'plane'
  /** 비워도 되는 칸(ref · 숫자) — 비우면 null 로 보낸다. */
  optional?: boolean
}

export interface OpSpec {
  op: string
  label: string
  group: '스케치' | '입체' | '조합' | '마감' | '배치' | '기준' | '영역'
  /** 툴바에 보일 짧은 이름. 없으면 label. */
  short?: string
  icon: LucideIcon
  help: string
  fields: FieldSpec[]
  /** 새 피처의 기본값. id · label 은 만들 때 붙인다. */
  defaults: Record<string, unknown>
}

const EDGE_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'vertical', label: '수직 엣지' },
  { value: 'horizontal', label: '수평 엣지' },
  { value: 'top', label: '윗면 둘레' },
  { value: 'bottom', label: '바닥면 둘레' },
]
const AXIS_OPTIONS = ['X', 'Y', 'Z'].map((a) => ({ value: a, label: a }))
const THREAD_OPTIONS = ['M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12'].map((one) => ({ value: one, label: one }))
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
    help: '평면 위의 2D 윤곽입니다. 도형을 더하거나(add) 빼서(cut) 작성합니다.',
    fields: [
      { key: 'plane', label: '평면', kind: 'plane' },
      { key: 'shapes', label: '도형', kind: 'shapes' },
      { key: 'hull', label: '볼록 껍질 윤곽 사용 (모든 도형을 감쌈)', kind: 'checkbox' },
      { key: 'offset', label: '윤곽 오프셋 (mm, 0: 없음, 음수: 안쪽)', kind: 'number', step: 0.1 },
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
    help: '스케치를 평면의 법선 방향으로 돌출하여 입체를 생성합니다.',
    fields: [
      { key: 'sketch', label: '스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'distance', label: '거리 (mm)', kind: 'number' },
      {
        key: 'direction',
        label: '방향',
        kind: 'select',
        options: [
          { value: 'normal', label: '법선 방향' },
          { value: 'reverse', label: '반대 방향' },
          { value: 'both', label: '양방향' },
        ],
      },
      { key: 'taper', label: '구배 (°, 양수: 끝으로 갈수록 좁아짐)', kind: 'number', step: 1 },
      {
        key: 'until',
        label: '돌출 범위',
        kind: 'select',
        options: [
          { value: 'distance', label: '지정 거리' },
          { value: 'next', label: '대상의 다음 면까지' },
          { value: 'last', label: '대상의 마지막 면까지 (관통)' },
        ],
      },
      { key: 'target', label: '종료 기준 대상 (면까지 돌출 시)', kind: 'ref', refKind: 'solid', optional: true },
    ],
    defaults: { sketch: '', distance: 10, direction: 'normal', taper: 0, until: 'distance', target: null },
  },
  {
    op: 'sweep',
    icon: Route,
    label: '스윕',
    group: '입체',
    help: '단면 스케치를 경로를 따라 스윕하여 입체를 생성합니다(파이프, 핸들, 홈 등). 스케치 평면의 원점이 경로의 첫 점에 오도록 배치하십시오.',
    fields: [
      { key: 'sketch', label: '단면 스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'path', label: '경로 점 (X, Y, Z)', kind: 'points3' },
      { key: 'smooth', label: '매끄러운 곡선으로 연결', kind: 'checkbox' },
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
    help: '측면에서 본 꺾은선을 따라 판을 접어 판금을 생성합니다(브래킷, ㄱ자 앵글, 덮개 등). 예: ‘2t 판, 30 상승 후 20 꺾임, 폭 40, 굽힘 R4’.',
    fields: [
      { key: 'thickness', label: '판 두께 (mm)', kind: 'number', step: 0.5 },
      { key: 'width', label: '폭 (mm, 돌출 길이)', kind: 'number' },
      { key: 'path', label: '꺾은선 (평면 위 X, Y)', kind: 'points' },
      { key: 'plane', label: '꺾은선 평면', kind: 'plane' },
      { key: 'bend_radius', label: '굽힘 안쪽 반지름 (mm, 0: 각진 모서리)', kind: 'number', step: 0.5 },
      {
        key: 'side',
        label: '두께 방향',
        kind: 'select',
        options: [
          { value: 'left', label: '꺾은선이 안쪽 면' },
          { value: 'right', label: '꺾은선이 바깥쪽 면' },
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
    op: 'bend',
    icon: FoldHorizontal,
    label: '판금 굽힘',
    short: '굽힘',
    group: '입체',
    help: '펼친 판을 굽힘선에서 접거나 원통에 감습니다. 구멍과 노치는 펼친 상태에서 모델링하십시오. 판의 두께는 균일해야 하며(포켓과 위아래 모서리 필렛은 굽힘 이후에 적용), 굽힘 구간의 구멍도 함께 휘어집니다. ‘다른 방향의 플랜지’로 상자 전개도의 네 변을 한 번에 접을 수 있습니다.',
    fields: [
      { key: 'target', label: '펼친 판', kind: 'ref', refKind: 'solid' },
      { key: 'along', label: '굽힘 진행 방향 (판 위, 굽힘선은 이 방향에 수직)', kind: 'xyz' },
      { key: 'bends', label: '굽힘 (시작점부터 순서대로)', kind: 'bends' },
      { key: 'also', label: '다른 방향의 플랜지 (상자형, 플랜지별 방향과 굽힘)', kind: 'bendgroups' },
      { key: 'corner_relief', label: '코너 릴리프 (플랜지가 모서리에서 겹칠 때)', kind: 'checkbox' },
      { key: 'k_factor', label: '중립면 위치 (K: 안쪽 면 기준 두께 비율, 일반적으로 0.3 ~ 0.5)', kind: 'number', step: 0.05 },
    ],
    defaults: {
      target: '',
      along: [1, 0, 0],
      bends: [{ at: 0, radius: 5, toward: 'up', until: 'angle', angle: 90 }],
      k_factor: 0.5,
    },
  },
  {
    op: 'surface',
    icon: Waves,
    label: '곡면',
    group: '입체',
    help: '입체가 아닌 곡면을 생성합니다. 점 격자를 지나는 자유 곡면(측정점 기반), 3D 곡선을 잇는 곡면, 닫힌 경계를 채우는 곡면을 지원합니다. 곡면은 그대로 최종 결과가 될 수 없으므로 ‘두께 부여’로 입체를 생성하거나 ‘자르기’의 분할 곡면으로 사용하십시오.',
    fields: [
      {
        key: 'kind',
        label: '생성 방식',
        kind: 'select',
        options: [
          { value: 'grid', label: '점 격자를 지나는 곡면' },
          { value: 'loft', label: '곡선을 잇는 곡면' },
          { value: 'fill', label: '경계를 채우는 곡면' },
        ],
      },
      { key: 'grid', label: '점 격자 (행별 점 목록 [[[x,y,z], …], …], 점 격자 방식에서 사용)', kind: 'json' },
      { key: 'curves', label: '곡선 (곡선별 점 목록 [[[x,y,z], …], …], 곡선 연결 방식에서 사용)', kind: 'json' },
      { key: 'boundary', label: '경계 점 (경계 채우기 방식에서 사용)', kind: 'points3' },
      { key: 'through', label: '통과할 내부 점 (경계 채우기 방식)', kind: 'points3' },
      { key: 'smooth', label: '곡선과 경계를 점을 통과하는 매끄러운 곡선으로 보간', kind: 'checkbox' },
      { key: 'ruled', label: '곡선 사이를 직선으로 연결', kind: 'checkbox' },
    ],
    defaults: {
      kind: 'grid',
      grid: [
        [
          [-40, -30, 0],
          [0, -30, 5],
          [40, -30, 0],
        ],
        [
          [-40, 0, 5],
          [0, 0, 10],
          [40, 0, 5],
        ],
        [
          [-40, 30, 0],
          [0, 30, 5],
          [40, 30, 0],
        ],
      ],
      smooth: true,
      ruled: false,
      through: [],
    },
  },
  {
    op: 'thicken',
    icon: Layers,
    label: '두께 부여',
    short: '두께',
    group: '입체',
    help: '곡면에 두께를 부여하여 입체를 생성합니다(곡면에 밀착하는 받침, 얇은 덮개 등). 앞쪽은 곡면의 법선 방향이며 점의 순서로 결정됩니다. 양쪽을 선택하면 두께를 절반씩 적용합니다.',
    fields: [
      { key: 'target', label: '곡면', kind: 'ref', refKind: 'any' },
      { key: 'thickness', label: '두께 (mm)', kind: 'number', step: 0.5 },
      {
        key: 'side',
        label: '두께 방향',
        kind: 'select',
        options: [
          { value: 'front', label: '앞 (법선 방향)' },
          { value: 'back', label: '뒤' },
          { value: 'both', label: '양쪽 (절반씩)' },
        ],
      },
    ],
    defaults: { target: '', thickness: 2, side: 'front' },
  },
  {
    op: 'deform',
    icon: Tornado,
    label: '비틀기·테이퍼',
    short: '비틀기',
    group: '입체',
    help: '축을 따라 단면을 회전(비틀기)하고 축소(테이퍼)합니다(비틀린 띠, 블레이드, 끝으로 갈수록 가늘어지는 보 등). 구간(시작 ~ 끝)에서 회전각은 0에서 지정 각도까지, 배율은 1에서 지정 배율까지 변합니다. 구간 앞쪽은 변형하지 않고, 구간 뒤쪽은 끝의 변형을 그대로 유지합니다. 구간을 지정하지 않으면 대상 전체에 적용합니다. 곡면은 NURBS로 근사합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'axis', label: '축 (원점 기준 X·Y·Z 또는 기준축)', kind: 'axisref' },
      { key: 'twist', label: '비틀림 각 (°, 끝 기준)', kind: 'number', step: 5 },
      { key: 'taper', label: '끝 단면 배율 (1: 변화 없음, 0.5: 절반)', kind: 'number', step: 0.05 },
      { key: 'start', label: '시작 위치 (축 위 mm, 미입력 시 대상의 시작)', kind: 'number', optional: true },
      { key: 'end', label: '끝 위치 (축 위 mm, 미입력 시 대상의 끝)', kind: 'number', optional: true },
    ],
    defaults: { target: '', axis: 'Z', twist: 90, taper: 1, start: null, end: null },
  },
  {
    op: 'unfold',
    icon: UnfoldHorizontal,
    label: '판금 전개',
    short: '전개',
    group: '입체',
    help: '굽힌 판(두께가 균일한 판금)을 펼친 형상으로 변환하여 XY 평면 위에 두께만큼 놓습니다. 레시피로 굽힌 판과 가져온 판금 STEP 모두 전개할 수 있습니다. 굽힘부는 중립면 길이로 전개하므로 K 값은 굽힘 시와 같아야 합니다. 굽힘선, 굽힘 방향, 각도가 포함된 DXF는 ‘파일 › 전개도’에서 다운로드하십시오.',
    fields: [
      { key: 'target', label: '굽힌 판', kind: 'ref', refKind: 'solid' },
      { key: 'k_factor', label: '중립면 위치 (K, 굽힘 시와 동일)', kind: 'number', step: 0.05 },
      { key: 'flip', label: '반대쪽 표면 기준 (굽힘의 위아래가 반전됨)', kind: 'checkbox' },
    ],
    defaults: { target: '', k_factor: 0.5, flip: false },
  },
  {
    op: 'frame',
    icon: Frame,
    label: '구조 프레임',
    short: '프레임',
    group: '입체',
    help: '알루미늄 프로파일, 각관, 원관, 앵글, 채널, H형강을 경로를 따라 배치합니다(지그의 받침 프레임, 기둥 등). 각 경로에서 점과 점 사이가 부재 하나이며, 마지막 점이 처음 점과 같으면 닫힌 프레임이 됩니다. 단면 중심은 경로 위에 놓이고 단면의 위쪽은 +Z 방향입니다(수직 부재는 +X).',
    fields: [
      { key: 'profile', label: '단면', kind: 'profile' },
      { key: 'paths', label: '경로 (점 사이마다 부재 하나)', kind: 'paths' },
      {
        key: 'corner',
        label: '코너 처리',
        kind: 'select',
        options: [
          { value: 'miter', label: '45° 마이터 (용접 프레임)' },
          { value: 'butt', label: '맞대기 (앞 부재 관통, 프로파일 조립)' },
          { value: 'none', label: '겹침' },
        ],
      },
      {
        key: 'meet',
        label: '다른 경로와 만나는 끝 (기둥 → 프레임)',
        kind: 'select',
        options: [
          { value: 'butt', label: '상대 부재 측면에 맞춤' },
          { value: 'overlap', label: '겹침 유지' },
        ],
      },
      { key: 'roll', label: '단면 회전 (°, 부재 축 기준)', kind: 'number', step: 90 },
      { key: 'separate', label: '부재 개별 유지 (결합하지 않음, 볼트 조립)', kind: 'checkbox' },
    ],
    defaults: {
      profile: { type: 't_slot', size: 40 },
      paths: [
        [
          [0, 0, 0],
          [500, 0, 0],
          [500, 300, 0],
          [0, 300, 0],
          [0, 0, 0],
        ],
      ],
      corner: 'butt',
      meet: 'butt',
      roll: 0,
      separate: false,
    },
  },
  {
    op: 'helix',
    icon: Spline,
    label: '나선',
    group: '입체',
    help: '단면 스케치를 나선 경로를 따라 스윕합니다(스프링, 나사산 등). 단면을 XY 원점에 작성하면 시작점에 맞게 배치됩니다. 단면이 피치보다 작아야 서로 겹치지 않습니다.',
    fields: [
      { key: 'sketch', label: '단면 스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'radius', label: '나선 반지름 (mm)', kind: 'number' },
      { key: 'pitch', label: '피치 (mm, 1회전당 상승 높이)', kind: 'number' },
      { key: 'height', label: '높이 (mm)', kind: 'number' },
      { key: 'axis', label: '축', kind: 'select', options: AXIS_OPTIONS },
      { key: 'at', label: '축 시작점', kind: 'xyz' },
      { key: 'lefthand', label: '왼나사 (반대 방향)', kind: 'checkbox' },
    ],
    defaults: { sketch: '', radius: 10, pitch: 5, height: 30, axis: 'Z', at: [0, 0, 0], lefthand: false },
  },
  {
    op: 'revolve',
    icon: RotateCw,
    label: '회전',
    group: '입체',
    help: '스케치를 축을 중심으로 회전하여 입체를 생성합니다.',
    fields: [
      { key: 'sketch', label: '스케치', kind: 'ref', refKind: 'sketch' },
      { key: 'axis', label: '축 (원점 기준 X·Y·Z 또는 기준축)', kind: 'axisref' },
      { key: 'angle', label: '각도 (°)', kind: 'number', step: 1 },
    ],
    defaults: { sketch: '', axis: 'Z', angle: 360 },
  },
  {
    op: 'box',
    icon: Box,
    label: '블록',
    group: '입체',
    help: '중심이 at인 직육면체(블록)입니다.',
    fields: [
      { key: 'length', label: '길이 X (mm)', kind: 'number' },
      { key: 'width', label: '너비 Y (mm)', kind: 'number' },
      { key: 'height', label: '높이 Z (mm)', kind: 'number' },
      { key: 'at', label: '기준 위치', kind: 'xyz' },
      { key: 'align', label: '정렬 기준 (치수를 맞출 기준 위치)', kind: 'align3' },
    ],
    defaults: { length: 40, width: 30, height: 20, at: [0, 0, 0], align: ['center', 'center', 'center'] },
  },
  {
    op: 'wedge',
    icon: Triangle,
    label: '쐐기',
    group: '입체',
    help: '경사 블록입니다. 밑면은 길이와 너비 그대로이고 윗면은 좁아집니다. 지그의 경사 받침이나 고임에 사용합니다.',
    fields: [
      { key: 'length', label: '길이 X (mm)', kind: 'number' },
      { key: 'width', label: '너비 Y (mm)', kind: 'number' },
      { key: 'height', label: '높이 Z (mm)', kind: 'number' },
      { key: 'top_x_min', label: '윗면 X 시작 (mm)', kind: 'number' },
      { key: 'top_x_max', label: '윗면 X 끝 (미입력 시 축소하지 않음)', kind: 'number' },
      { key: 'top_z_min', label: '윗면 Z 시작 (mm)', kind: 'number' },
      { key: 'top_z_max', label: '윗면 Z 끝 (미입력 시 축소하지 않음)', kind: 'number' },
      { key: 'at', label: '기준 위치', kind: 'xyz' },
      { key: 'align', label: '정렬 기준', kind: 'align3' },
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
    op: 'bolt',
    icon: Wrench,
    label: '볼트',
    group: '입체',
    help: '머리, 와셔, 몸통으로 구성됩니다. 기준점은 머리가 안착하는 면 위의 점이며, 몸통은 아래(-Z) 방향으로 생성됩니다. 나사산은 표현하지 않으며 치수는 ISO 비례를 따릅니다.',
    fields: [
      { key: 'at', label: '머리 안착점', kind: 'xyz' },
      { key: 'nominal', label: '호칭 지름 (M6: 6)', kind: 'number' },
      { key: 'length', label: '몸통 길이 (mm)', kind: 'number' },
      {
        key: 'head',
        label: '머리 형상',
        kind: 'select',
        options: [
          { value: 'hex', label: '육각' },
          { value: 'socket', label: '소켓 (원통)' },
        ],
      },
      { key: 'washer', label: '와셔', kind: 'checkbox' },
      { key: 'down', label: '몸통 아래 방향 (-Z)', kind: 'checkbox' },
    ],
    defaults: { at: [0, 0, 0], nominal: 8, length: 30, head: 'hex', washer: true, down: true },
  },
  {
    op: 'pin',
    icon: Wrench,
    label: '위치 핀',
    group: '입체',
    help: '끝단을 모따기한 원기둥입니다. 기준점은 밑면 중심이며 위(+Z) 방향으로 생성됩니다.',
    fields: [
      { key: 'at', label: '밑면 중심', kind: 'xyz' },
      { key: 'diameter', label: '지름 (mm)', kind: 'number' },
      { key: 'length', label: '길이 (mm)', kind: 'number' },
      { key: 'chamfer', label: '끝단 모따기 (mm)', kind: 'number', step: 0.1 },
    ],
    defaults: { at: [0, 0, 0], diameter: 8, length: 25, chamfer: 0.8 },
  },
  {
    op: 'nut',
    icon: Hexagon,
    label: '너트',
    group: '입체',
    help: '육각 너트(ISO 4032)입니다. 기준점은 너트가 안착하는 면 위의 점이며, 지정한 방향으로 생성됩니다.',
    fields: [
      { key: 'at', label: '안착점', kind: 'xyz' },
      { key: 'thread', label: '나사 규격', kind: 'select', options: THREAD_OPTIONS },
      { key: 'direction', label: '생성 방향', kind: 'xyz' },
    ],
    defaults: { at: [0, 0, 0], thread: 'M6', direction: [0, 0, 1] },
  },
  {
    op: 'washer',
    icon: Disc,
    label: '와셔',
    group: '입체',
    help: '평와셔(ISO 7089)입니다. 기준점은 와셔가 안착하는 면 위의 점이며, 지정한 방향으로 생성됩니다.',
    fields: [
      { key: 'at', label: '안착점', kind: 'xyz' },
      { key: 'thread', label: '나사 규격', kind: 'select', options: THREAD_OPTIONS },
      { key: 'direction', label: '생성 방향', kind: 'xyz' },
    ],
    defaults: { at: [0, 0, 0], thread: 'M6', direction: [0, 0, 1] },
  },
  {
    op: 'bearing',
    icon: Cog,
    label: '베어링',
    group: '입체',
    help: '깊은 홈 볼 베어링입니다. 내륜과 외륜을 하나의 링으로 단순화합니다. 기준점은 한쪽 측면의 중심이며, 지정한 방향으로 폭만큼 생성됩니다.',
    fields: [
      { key: 'at', label: '한쪽 측면 중심', kind: 'xyz' },
      {
        key: 'designation',
        label: '호칭 번호',
        kind: 'select',
        options: ['625', '626', '608', '6000', '6001', '6002', '6003', '6004', '6005', '6200', '6201', '6202', '6203', '6204', '6205'].map((one) => ({ value: one, label: one })),
      },
      { key: 'direction', label: '축 방향', kind: 'xyz' },
    ],
    defaults: { at: [0, 0, 0], designation: '608', direction: [0, 0, 1] },
  },
  {
    op: 'spring',
    icon: Paperclip,
    label: '압축 스프링',
    short: '스프링',
    group: '입체',
    help: '선 지름, 평균 지름, 자유 길이, 감김 수로 정의합니다. 기준점은 밑면 중심이며 지정한 방향으로 생성됩니다.',
    fields: [
      { key: 'at', label: '밑면 중심', kind: 'xyz' },
      { key: 'wire', label: '선 지름 (mm)', kind: 'number', step: 0.1 },
      { key: 'diameter', label: '평균 지름 (mm)', kind: 'number' },
      { key: 'length', label: '자유 길이 (mm)', kind: 'number' },
      { key: 'coils', label: '감김 수', kind: 'number', step: 0.5 },
      { key: 'direction', label: '축 방향', kind: 'xyz' },
    ],
    defaults: { at: [0, 0, 0], wire: 2, diameter: 16, length: 50, coils: 8, direction: [0, 0, 1] },
  },
  {
    op: 'bracket',
    icon: CornerDownRight,
    label: '코너 브래킷',
    short: '브래킷',
    group: '입체',
    help: '알루미늄 프로파일용 코너 브래킷(L형, 근사 치수)입니다. 기준점은 두 프로파일 면이 만나는 안쪽 모서리의 점이며, 두 다리의 방향(서로 수직)을 지정합니다.',
    fields: [
      { key: 'at', label: '안쪽 모서리 점', kind: 'xyz' },
      { key: 'size', label: '프로파일 계열', kind: 'select', options: ['20', '30', '40', '45'].map((one) => ({ value: one, label: one })) },
      { key: 'legs', label: '두 다리 방향', kind: 'points3' },
    ],
    defaults: {
      at: [0, 0, 0],
      size: 40,
      legs: [
        [1, 0, 0],
        [0, 0, 1],
      ],
    },
  },
  {
    op: 'fasten',
    icon: Bolt,
    label: '구멍 기준 체결 부품 배치',
    short: '체결',
    group: '배치',
    help: '규칙으로 검색한 구멍마다 볼트, 너트, 와셔, 핀을 구멍 축에 배치합니다. 좌표를 사용하지 않으므로 치수가 변경되어도 위치가 함께 갱신됩니다. 나사 규격을 지정하지 않으면 구멍 지름에 맞게 선택하며, 카운터보어 구멍이면 단차면에 안착합니다.',
    fields: [
      { key: 'target', label: '구멍이 있는 입체', kind: 'ref', refKind: 'solid' },
      { key: 'holes', label: '구멍 선택 (recipe_find 질의)', kind: 'query' },
      {
        key: 'part',
        label: '배치할 부품',
        kind: 'select',
        options: [
          { value: 'bolt', label: '볼트' },
          { value: 'nut', label: '너트' },
          { value: 'washer', label: '와셔' },
          { value: 'pin', label: '핀 (구멍 지름과 동일)' },
        ],
      },
      { key: 'thread', label: '나사 규격', kind: 'select', options: [{ value: '__none__', label: '구멍 지름 기준' }, ...THREAD_OPTIONS] },
      { key: 'length', label: '길이 (mm, 미입력 시 구멍 깊이)', kind: 'number', optional: true },
      {
        key: 'head',
        label: '볼트 머리',
        kind: 'select',
        options: [
          { value: 'socket', label: '소켓 (원통)' },
          { value: 'hex', label: '육각' },
        ],
      },
      { key: 'washer', label: '볼트 머리 아래 와셔', kind: 'checkbox' },
      {
        key: 'side',
        label: '배치할 구멍 끝',
        kind: 'select',
        options: [
          { value: 'top', label: '위 (+Z)' },
          { value: 'bottom', label: '아래' },
        ],
      },
    ],
    defaults: { target: '', holes: { kind: 'cylinder' }, part: 'bolt', thread: null, length: null, head: 'socket', washer: false, side: 'top' },
  },
  {
    op: 'standoff',
    icon: Wrench,
    label: '스페이서',
    group: '입체',
    help: '중심에 구멍이 있는 원통(스탠드오프)입니다. 기준점은 밑면 중심입니다.',
    fields: [
      { key: 'at', label: '밑면 중심', kind: 'xyz' },
      { key: 'outer', label: '바깥 지름 (mm)', kind: 'number' },
      { key: 'hole', label: '구멍 지름 (mm)', kind: 'number' },
      { key: 'height', label: '높이 (mm)', kind: 'number' },
    ],
    defaults: { at: [0, 0, 0], outer: 16, hole: 8.5, height: 10 },
  },
  {
    op: 'cylinder',
    icon: Cylinder,
    label: '원통',
    group: '입체',
    help: '중심이 at인 원통입니다.',
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
    help: '중심이 at인 구입니다.',
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
    help: '밑면 중심이 at인 원뿔입니다. 윗면 반지름이 0이면 꼭짓점이 뾰족해집니다.',
    fields: [
      { key: 'bottom_radius', label: '밑면 반지름 (mm)', kind: 'number' },
      { key: 'top_radius', label: '윗면 반지름 (mm)', kind: 'number' },
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
    help: '도넛 형상입니다. 큰 반지름(중심선)과 작은 반지름(관 단면)으로 정의합니다.',
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
    help: '두 개 이상의 스케치를 연결하여 입체를 생성합니다. 서로 다른 높이의 평면에 스케치를 배치하고 순서대로 선택하십시오.',
    fields: [
      {
        key: 'sketches',
        label: '스케치 (순서대로)',
        kind: 'refs',
        refKind: 'sketch',
      },
      { key: 'ruled', label: '직선 연결 (각진 전이)', kind: 'checkbox' },
    ],
    defaults: { sketches: [], ruled: false },
  },
  {
    op: 'union',
    icon: Combine,
    label: '결합',
    group: '조합',
    help: '여러 입체를 하나로 합칩니다(합집합).',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'solid' }],
    defaults: { targets: [] },
  },
  {
    op: 'group',
    icon: Group,
    label: '그룹',
    group: '조합',
    help: '여러 형상을 결합하지 않고 하나의 그룹으로 구성합니다. 주로 조립 레시피의 마지막 단계에 사용합니다. 결합(union)과 달리 각 솔리드가 개별로 유지됩니다.',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'any' }],
    defaults: { targets: [] },
  },
  {
    op: 'component',
    icon: PackagePlus,
    label: '가져오기',
    group: '조합',
    help: '다른 도면(부품, 지그)을 통째로 가져와 배치합니다. 가져온 도면의 변수를 재정의하여 조립 변수로 제어할 수 있습니다. 일반적으로 ‘조립’ 화면에서 다룹니다.',
    fields: [
      { key: 'source', label: '가져올 도면 (part:…, jig:…, work:…)', kind: 'text' },
      { key: 'translate', label: '위치', kind: 'xyz' },
      { key: 'rotate', label: '회전 (°)', kind: 'xyz' },
    ],
    defaults: { source: '', translate: [0, 0, 0], rotate: [0, 0, 0], params: {} },
  },
  {
    op: 'cut',
    icon: Scissors,
    label: '빼기',
    group: '조합',
    help: '대상에서 도구 형상을 뺍니다(차집합).',
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
    help: '겹치는 부분만 남깁니다(교집합).',
    fields: [{ key: 'targets', label: '대상', kind: 'refs', refKind: 'solid' }],
    defaults: { targets: [] },
  },
  {
    op: 'fillet',
    icon: Radius,
    label: '블렌드',
    group: '마감',
    help: '엣지를 둥글게 처리합니다(필렛, 라운드). 반지름은 인접 면보다 작아야 합니다. 끝 반지름을 지정하면 엣지를 따라 반지름이 일정하게 변합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'edges', label: '엣지', kind: 'select', options: EDGE_OPTIONS },
      { key: 'radius', label: '반지름 (mm)', kind: 'number' },
      { key: 'radius_end', label: '끝 반지름 (mm, 미입력 시 일정)', kind: 'number', optional: true },
      { key: 'start', label: '‘반지름’ 쪽 끝 근처의 점 (끝 반지름 지정 시)', kind: 'xyz' },
    ],
    defaults: { target: '', edges: 'vertical', radius: 2 },
  },
  {
    op: 'split',
    icon: SquareSplitHorizontal,
    label: '자르기',
    group: '조합',
    help: '평면으로 자릅니다(반쪽 지그, 단면 확인 등). ‘위’는 평면의 법선 방향입니다. ‘분할 곡면’을 선택하면 평면 대신 해당 곡면으로 자르며(위는 곡면의 앞쪽), 굽은 면을 따라 잘라 낸 네스트를 생성할 수 있습니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'plane', label: '절단 평면', kind: 'plane' },
      { key: 'tool', label: '분할 곡면 (미입력 시 평면 사용)', kind: 'ref', refKind: 'any', optional: true },
      {
        key: 'keep',
        label: '유지할 쪽',
        kind: 'select',
        options: [
          { value: 'top', label: '위 (법선 방향)' },
          { value: 'bottom', label: '아래' },
          { value: 'both', label: '양쪽' },
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
    help: '입체를 평면으로 자른 단면을 스케치로 생성합니다. 오프셋을 적용하여 돌출하면 해당 높이의 포켓 윤곽이 됩니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'plane', label: '절단 평면', kind: 'plane' },
      { key: 'offset', label: '윤곽 오프셋 (mm)', kind: 'number', step: 0.1 },
    ],
    defaults: { target: '', plane: { name: 'XY', origin: [0, 0, 0] }, offset: 0 },
  },
  {
    op: 'imprint',
    icon: Stamp,
    label: '접촉 영역 임프린트',
    short: '임프린트',
    group: '영역',
    help: '조립(그룹)에서 바디끼리 접촉하는 영역을 서로의 면에 임프린트하여 분할합니다. 예를 들어 판 위에 블록이 있으면 판 윗면이 ‘블록과 접촉하는 영역’과 나머지로 분할되어 접촉면 쌍의 면적과 위치가 정확히 일치합니다. 접촉 영역마다 ‘받침판/블록’(받침판 쪽), ‘블록/받침판’(블록 쪽) 태그가 붙으며, 시뮬레이션 조건에서 이 태그를 선택합니다. 서로 겹치는(간섭) 바디는 허용하지 않습니다.',
    fields: [{ key: 'target', label: '조립 (그룹)', kind: 'ref', refKind: 'solid' }],
    defaults: { target: '' },
  },
  {
    op: 'divide_face',
    icon: SquareDashedBottom,
    label: '면 분할',
    group: '영역',
    help: '면을 여러 영역으로 분할하여 하중이나 접촉을 면의 일부에만 적용할 수 있게 합니다. 원, 사각형 또는 면 위에 작성한 스케치 형상(여러 도형, 고리 형상 포함)으로 분할합니다. 형상 자체는 변하지 않습니다(부피 변화 없음). 분할된 영역에 지정한 이름은 ‘시뮬레이션 조건’ 탭에서 선택 그룹으로 사용합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      {
        key: 'shape',
        label: '분할 형상',
        kind: 'select',
        options: [
          { value: 'circle', label: '원' },
          { value: 'rect', label: '사각형' },
          { value: 'sketch', label: '스케치 형상' },
        ],
      },
      { key: 'radius', label: '반지름 (mm, 원)', kind: 'number' },
      { key: 'size', label: '가로·세로 (mm, 사각형)', kind: 'xy' },
      { key: 'at', label: '중심 (x, y, z, 원·사각형일 때)', kind: 'xyz' },
      { key: 'sketch', label: '스케치 (스케치 형상일 때, 분할할 면 위에 작성한 스케치이며 해당 면이 자동 선택됨)', kind: 'ref', refKind: 'sketch', optional: true },
      { key: 'tag', label: '이름', kind: 'text' },
    ],
    defaults: { target: '', on: { role: 'top' }, shape: 'circle', radius: 8, tag: '패치' },
  },
  {
    op: 'chamfer',
    icon: Diamond,
    label: '챔퍼',
    group: '마감',
    help: '엣지를 비스듬히 깎습니다(모따기). 두 거리(비대칭) 또는 거리와 각도로 지정합니다. 길이는 기준면에서 측정하며, 기준면을 선택하지 않으면 두 면 중 위(+Z)를 향하는 면이 기준이 됩니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'edges', label: '엣지', kind: 'select', options: EDGE_OPTIONS },
      { key: 'length', label: '길이 (mm, 기준면 쪽)', kind: 'number' },
      { key: 'length2', label: '다른 면 쪽 길이 (mm, 비대칭, 미입력 시 동일 길이)', kind: 'number', optional: true },
      { key: 'angle', label: '각도 (°, 거리-각도 방식, 두 거리 방식과 함께 사용 불가)', kind: 'number', optional: true },
      { key: 'reference', label: '기준면 (3D에서 선택)', kind: 'facepicks' },
    ],
    defaults: { target: '', edges: 'all', length: 1 },
  },
  {
    op: 'hole',
    icon: CircleDot,
    label: '구멍',
    group: '마감',
    help: '단순, 카운터보어, 카운터싱크, 탭 구멍을 생성합니다. 나사 규격(M3~M12)을 선택하면 치수가 규격표에서 자동으로 입력됩니다. 면을 지정하지 않으면 윗면(+Z)에서 아래 방향으로 가공합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      {
        key: 'kind',
        label: '종류',
        kind: 'select',
        options: [
          { value: 'simple', label: '단순 (관통/막힘)' },
          { value: 'counterbore', label: '카운터보어' },
          { value: 'countersink', label: '카운터싱크' },
          { value: 'tap', label: '탭 (나사 구멍)' },
        ],
      },
      {
        key: 'thread',
        label: '나사 규격 (미선택 시 지름 직접 입력)',
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
        label: '지름 (mm, 나사 규격 선택 시 생략 가능)',
        kind: 'number',
      },
      { key: 'depth', label: '깊이 (mm, 미입력 시 관통)', kind: 'number' },
      { key: 'counter_diameter', label: '카운터 지름 (mm)', kind: 'number' },
      { key: 'counter_depth', label: '카운터보어 깊이 (mm)', kind: 'number' },
      {
        key: 'countersink_angle',
        label: '카운터싱크 각도 (°)',
        kind: 'number',
        step: 1,
      },
      { key: 'plane', label: '가공 면', kind: 'holeplane' },
      { key: 'at', label: '위치 (면 위 X, Y)', kind: 'points' },
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
    help: '내부를 비웁니다. 개방할 면을 선택하면 해당 면이 열리고 나머지는 일정 두께의 벽이 됩니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'thickness', label: '두께 (mm)', kind: 'number' },
      { key: 'open', label: '개방 면', kind: 'faceselect' },
    ],
    defaults: { target: '', thickness: 2, open: 'top' },
  },
  {
    op: 'offset',
    icon: Expand,
    label: '오프셋',
    group: '마감',
    help: '형상 전체를 두껍게(+) 또는 얇게(−) 오프셋합니다. 제품 형상을 간극만큼 키워서 빼면 지그 포켓이 됩니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'amount', label: '오프셋 거리 (mm, 음수: 축소)', kind: 'number', step: 0.1 },
      {
        key: 'corners',
        label: '모서리 형상',
        kind: 'select',
        options: [
          { value: 'round', label: '둥근 모서리' },
          { value: 'sharp', label: '각진 모서리' },
        ],
      },
    ],
    defaults: { target: '', amount: 0.5, corners: 'round' },
  },
  {
    op: 'defeature',
    icon: Eraser,
    label: '면 삭제',
    group: '마감',
    help: '작은 구멍, 필렛 또는 선택한 면을 삭제하고 인접 면을 연장하여 메웁니다(해석용 형상 단순화, 가져온 STEP 수정 등). 기준값(지름, 반지름)으로 선택한 면은 DOE에서 치수가 변경되면 설계점마다 다시 판정합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      { key: 'faces', label: '선택한 면 (3D에서 선택)', kind: 'facepicks' },
      { key: 'holes_below', label: '이 지름 미만의 구멍 (mm, 미입력 시 삭제하지 않음)', kind: 'number', step: 0.5, optional: true },
      { key: 'fillets_below', label: '이 반지름 미만의 필렛 (mm, 미입력 시 삭제하지 않음)', kind: 'number', step: 0.5, optional: true },
    ],
    defaults: { target: '', faces: 'none', holes_below: 6, fillets_below: 2 },
  },
  {
    op: 'draft',
    icon: Waves,
    label: '구배',
    group: '마감',
    help: '선택한 면을 기울입니다. 기준 평면과 만나는 위치의 치수는 유지됩니다. 탈형이 쉬운 포켓이나 금형에 사용합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'solid' },
      {
        key: 'faces',
        label: '면',
        kind: 'select',
        options: [
          { value: 'sides', label: '옆면 전체' },
          { value: 'top', label: '윗면' },
          { value: 'bottom', label: '바닥면' },
          { value: 'all', label: '모든 면' },
        ],
      },
      { key: 'angle', label: '각도 (°)', kind: 'number', step: 0.5 },
      { key: 'neutral', label: '기준 평면 (치수가 유지되는 위치)', kind: 'plane' },
    ],
    defaults: { target: '', faces: 'sides', angle: 3, neutral: { name: 'XY', origin: [0, 0, 0] } },
  },
  {
    op: 'pattern',
    icon: Grid3x3,
    label: '패턴',
    group: '배치',
    help: '피처를 여러 개 복제합니다. 결과는 그룹이므로 ‘빼기’의 도구나 ‘결합’의 대상으로 사용합니다.',
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
      { key: 'count', label: '개수 (격자는 X 방향)', kind: 'number', step: 1 },
      { key: 'spacing', label: '간격 (직선, 격자 X)', kind: 'xyz' },
      { key: 'count_y', label: '격자 Y 개수', kind: 'number', step: 1 },
      { key: 'spacing_y', label: '격자 Y 간격', kind: 'xyz' },
      { key: 'axis', label: '축 (원형, 원점 기준 X·Y·Z 또는 기준축)', kind: 'axisref' },
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
    help: '크기를 변경하고 회전한 뒤 이동합니다. 회전과 배율은 중심점을 기준으로 적용합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'any' },
      { key: 'translate', label: '이동', kind: 'xyz' },
      { key: 'rotate', label: '회전 (°)', kind: 'xyz' },
      { key: 'pivot', label: '회전·배율 중심', kind: 'xyz' },
      { key: 'scale', label: '배율 (1: 변화 없음)', kind: 'number', step: 0.1 },
    ],
    defaults: { target: '', translate: [0, 0, 0], rotate: [0, 0, 0], pivot: [0, 0, 0], scale: 1 },
  },
  {
    op: 'mirror',
    icon: FlipHorizontal,
    label: '미러',
    group: '배치',
    help: '평면을 기준으로 대칭 복사합니다.',
    fields: [
      { key: 'target', label: '대상', kind: 'ref', refKind: 'any' },
      { key: 'plane', label: '대칭 평면 (원점을 지나는 평면 또는 기준면)', kind: 'planeref' },
      { key: 'keep_original', label: '원본 유지', kind: 'checkbox' },
    ],
    defaults: { target: '', plane: 'YZ', keep_original: true },
  },
  {
    op: 'datum_axis',
    icon: Axis3d,
    label: '기준축',
    group: '기준',
    help: '형상을 생성하지 않는 기준축입니다. 회전과 원형 패턴의 회전축으로 사용합니다. 점과 방향, 두 점, 구멍(원통면)의 축 또는 직선 엣지에서 추출하며, 치수가 변경되면 함께 갱신됩니다.',
    fields: [{ key: 'origin', label: '정의 방식', kind: 'datumaxis' }],
    defaults: { origin: [0, 0, 0], direction: [0, 0, 1] },
  },
  {
    op: 'datum_plane',
    icon: SquareDashed,
    label: '기준면',
    group: '기준',
    help: '형상을 생성하지 않는 기준면입니다. 스케치, 자르기, 단면, 미러의 평면 입력란에서 선택합니다. 이름 있는 평면, 세 점 또는 형상의 평면에서 추출한 뒤 오프셋(offset)하고 축을 기준으로 기울일 수 있습니다(hinge, angle).',
    fields: [
      { key: 'plane', label: '정의 방식', kind: 'datumplane' },
      { key: 'offset', label: '오프셋 (mm, 법선 방향, 음수: 반대 방향)', kind: 'number', step: 1 },
      { key: 'hinge', label: '기울기 축 (미지정 시 기울이지 않음)', kind: 'axisref', optional: true },
      { key: 'angle', label: '기울기 각도 (°)', kind: 'number', step: 5 },
    ],
    defaults: { plane: { name: 'XY', origin: [0, 0, 0] }, offset: 10, hinge: null, angle: 0 },
  },
  {
    op: 'import_step',
    icon: Import,
    label: 'STEP 가져오기',
    group: '입체',
    help: '업로드한 STEP(작업물 id)입니다. ‘STEP 업로드’로 생성되므로 직접 입력하지 않습니다.',
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
  { value: 'constrained', label: '구속 윤곽' },
  { value: 'path', label: '선 (두께)' },
  { value: 'rounded_rect', label: '둥근 사각형' },
  { value: 'trapezoid', label: '사다리꼴' },
  { value: 'triangle', label: '삼각형 (변·각)' },
  { value: 'ellipse', label: '타원' },
  { value: 'text', label: '텍스트' },
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
    case 'constrained':
      // 점을 대충 두고 관계 · 치수로 정한다 — 처음은 왼쪽 아래를 고정한 40 x 30 네모.
      return { type, ...defaultConstrained(), ...base }
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
export function nodeKind(node: RecipeNode, nodes: RecipeNode[]): 'sketch' | 'solid' | 'axis' | 'plane' {
  if (node.op === 'datum_axis') return 'axis'
  if (node.op === 'datum_plane') return 'plane'
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
  // 기준 — 축 · 평면 칸의 값이 전역 이름(X · XY …)이 아니면 앞의 기준축 · 기준면이다.
  const axisRefs = [node.op === 'revolve' || node.op === 'pattern' ? node.axis : null, node.op === 'datum_plane' ? node.hinge : null]
  for (const value of axisRefs) if (typeof value === 'string' && value && !GLOBAL_AXES.has(value)) out.push(value)
  if (node.op === 'mirror' && typeof node.plane === 'string' && !GLOBAL_PLANES.has(node.plane)) out.push(node.plane)
  for (const value of Object.values(node)) {
    const datum = value && typeof value === 'object' ? (value as { datum?: unknown }).datum : null
    if (typeof datum === 'string' && datum) out.push(datum)
  }
  return out
}

/** 원점을 지나는 축 · 평면의 이름 — 축 · 평면 칸에서 기준 id 대신 쓴다(서버 `GLOBAL_AXES` · `GLOBAL_PLANES`). */
export const GLOBAL_AXES = new Set(['X', 'Y', 'Z'])
export const GLOBAL_PLANES = new Set(['XY', 'XZ', 'YZ', 'YX', 'ZX', 'ZY'])

export function nodesOf(recipe: Recipe): RecipeNode[] {
  return recipe.nodes as RecipeNode[]
}

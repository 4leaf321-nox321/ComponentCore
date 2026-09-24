import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { ConditionsPanel } from '@/modules/conditions/ConditionsPanel'

/**
 * 3D 대신 단추 몇 개 — 면 둘 · 점 · 바디를 찍는 것만 흉내 낸다. 누를 때 Ctrl · Shift 를
 * 함께 누르면(`fireEvent.click(단추, { ctrlKey: true })`) 뷰어처럼 그 키를 넘긴다.
 */
/** 뷰어가 받은 거르개 — 「켠 것 하나만」 을 시험이 볼 수 있게 내놓는다. */
let lastKinds: Record<string, boolean> | undefined
/** 3D 가 받은 파트 색 · 강조 — 트리에서 지정한 것이 3D 에도 보이는지 본다. */
let lastColors: Record<string, number> | undefined
let lastEmphasis: string | null | undefined
/** 3D 에 표시한 것 — 담은 것에 번호가 붙는지 본다. */
let lastMarks: { labels: { text: string }[] } | undefined
vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({
    onMeasure,
    onBoxSelect,
    measureKinds,
    measureMarks,
    partColors,
    emphasis,
  }: {
    onMeasure?: (pick: unknown, modifiers: { ctrl: boolean; shift: boolean }) => void
    onBoxSelect?: (picks: unknown[], modifiers: { ctrl: boolean; shift: boolean }) => void
    measureKinds?: Record<string, boolean>
    measureMarks?: { labels: { text: string }[] }
    partColors?: Record<string, number>
    emphasis?: string | null
  }) => {
    lastKinds = measureKinds
    lastColors = partColors
    lastEmphasis = emphasis
    lastMarks = measureMarks
    const keys = (e: React.MouseEvent) => ({ ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey })
    return (
      <div>
        <button onClick={(e) => onMeasure?.({ kind: 'face', face: { index: 0, center: [0, 0, 0] } }, keys(e))}>
          면 찍기
        </button>
        <button onClick={(e) => onMeasure?.({ kind: 'face', face: { index: 1, center: [5, 0, 9] } }, keys(e))}>
          다른 면 찍기
        </button>
        <button onClick={(e) => onMeasure?.({ kind: 'point', at: [1, 2, 3] }, keys(e))}>점 찍기</button>
        <button onClick={(e) => onMeasure?.({ kind: 'body', name: '기둥' }, keys(e))}>바디 찍기</button>
        {/* Shift + 끌기 — 사각형 안의 두 면(아래 · 위). */}
        <button
          onClick={() =>
            onBoxSelect?.(
              [
                { kind: 'face', face: { index: 0, center: [0, 0, 0] } },
                { kind: 'face', face: { index: 1, center: [5, 0, 9] } },
              ],
              { ctrl: false, shift: true },
            )
          }
        >
          사각형 선택
        </button>
      </div>
    )
  },
}))
vi.mock('@/modules/cad/useRecipeMesh', () => ({
  useRecipeMesh: () => ({ mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] }, problems: [] }),
}))

const SCHEMA = {
  schema_version: 1,
  units: { system: 'mm_n_tonne' },
  // **닫히는 계만** 고를 수 있다 — 낱낱이 적게 두면 `mm·kg·s·N` 같은 조합이 새어 든다.
  unit_systems: [
    { key: 'mm_n_tonne', label: 'mm · tonne · s (힘 N · 응력 MPa)', stress: 'MPa', mass: 'tonne' },
    { key: 'si', label: 'SI — m · kg · s (힘 N · 응력 Pa)', stress: 'Pa', mass: 'kg' },
  ],
  analysis: { properties: { type: { enum: ['modal', 'static'] }, modes: { type: 'integer' } } },
  groups: {
    constraints: {
      label: '구속',
      types: ['fixed_support', 'displacement'],
      fields: { name: {}, type: { enum: ['fixed_support', 'displacement'] }, on: {}, x: { anyOf: [{ type: 'number' }, { type: 'null' }] } },
      required: [],
    },
    loads: {
      label: '하중',
      types: ['pressure', 'bolt_pretension'],
      fields: { name: {}, type: { enum: ['pressure'] }, on: {}, magnitude: { anyOf: [{ type: 'number' }] }, unit: { type: 'string' } },
      required: [],
    },
    contacts: { label: '접촉', types: ['bonded'], fields: { name: {}, type: { enum: ['bonded'] }, source: {}, target: {} }, required: [] },
    initial: { label: '초기조건', types: ['environment_temperature'], fields: { type: { enum: ['environment_temperature'] }, on: {}, value: { anyOf: [{ type: 'number' }] } }, required: [] },
    mesh_hints: { label: '메시 힌트', types: [], fields: { on: {}, element_size: { anyOf: [{ type: 'number' }] } }, required: [] },
  },
  entities: ['face', 'edge', 'vertex', 'body'],
}

const CANDIDATES = {
  picked: { kind: 'plane' },
  candidates: [
    { label: 'bottom 면', select: { what: 'faces', role: 'bottom' }, matches: 1 },
    { label: '이 자리의 면', select: { what: 'faces', near: [0, 0, 0], limit: 1 }, matches: 1 },
  ],
}
/** 다른 자리(윗면)를 찍으면 다른 후보가 온다 — 여럿을 묶는 시험이 쓴다. */
const TOP_CANDIDATES = {
  picked: { kind: 'plane' },
  candidates: [
    { label: 'top 면', select: { what: 'faces', role: 'top' }, matches: 1 },
    { label: '이 자리의 면', select: { what: 'faces', near: [5, 0, 9], limit: 1 }, matches: 1 },
  ],
}

const RECIPE = { params: {}, nodes: [] }

/** 가짜 물성 — MatNexus 가 주는 모양 그대로(단위가 값에 붙어 있다). */
const MATERIALS = {
  fallback: false,
  items: [
    {
      code: 'M-000123',
      id: '8f0e',
      name: 'SPCC 1.2t',
      alias: '냉연강판',
      family: '강판',
      category: '냉연',
      grade: 'SPCC',
      density: 7850,
      density_unit: 'kg/m^3',
      poisson_ratio: 0.3,
      declared_count: 1,
      source: 'matnexus',
      // **서버가 환산해 준다** — 화면은 제 손으로 계산하지 않는다(환산표가 두 벌이 되면
      // 어느 날 어긋나고, 그때 보여 준 값과 내보낸 값이 달라진다). 206 GPa → 206000 MPa.
      converted: {
        system: 'mm_n_tonne',
        density: 7.85e-9,
        density_unit: 'tonne/mm3',
        properties: [
          {
            item: '탄성계수',
            unit: 'MPa',
            points: [
              { temperature_C: 22, value: 206000 },
              { temperature_C: 400, value: 170000 },
            ],
          },
        ],
      },
      payload: {
        code: 'M-000123',
        declared_properties: [
          {
            item: '탄성계수',
            si_unit: 'Pa',
            points: [
              { temperature_C: 22, value_si: 2.06e11 },
              { temperature_C: 400, value_si: 1.7e11 },
            ],
          },
        ],
      },
    },
  ],
}

MATERIALS.items.push({
  ...MATERIALS.items[0],
  code: 'M-000124',
  id: '9a1b',
  name: 'AL6061-T6',
  alias: '알루미늄 6061',
  family: '비철',
  category: '알루미늄',
  grade: '6061-T6',
})

/** 쪽(族) · 갈래 — 탐색기가 좁혀 들어갈 두 칸. 개수는 그쪽이 세어 준다. */
const CLASSES = { fallback: false, items: [{ family: '강판', category: '냉연', count: 1 }] }

/** 조립의 바디 둘 — 물성이 붙을 자리. 단품이면 「전체」 하나뿐이라 칸이 안 뜬다. */
const BODIES = {
  items: [
    { name: '바닥판', volume: 38400, step_product: 'body_1' },
    { name: '기둥', volume: 9425, step_product: 'body_2' },
  ],
}

vi.mock('@/shared/api/client', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@/shared/api/client')
  return {
    ...actual,
    api: {
      get: vi.fn(async (path: string) =>
        // **분류와 목록은 다른 길이다** — 탐색기의 첫 두 칸이 분류에서 나온다.
        path.startsWith('/materials/classifications')
          ? CLASSES
          : path.startsWith('/materials')
            ? MATERIALS
            : SCHEMA,
      ),
      // 바디 목록과 셀렉터 후보는 **다른 길**이다 — 물성이 어디에 붙는지가 바디에서 나온다.
      post: vi.fn(async (path: string, body?: { pick?: { point?: number[] }; picks?: { point: number[] }[] }) => {
        if (path.startsWith('/cad/recipe/bodies')) return BODIES
        const answer = (point?: number[]) => (point?.[0] === 5 ? TOP_CANDIDATES : CANDIDATES)
        // 여럿을 한 번에(사각형 선택) — 같은 순서로.
        if (body?.picks) return { items: body.picks.map((one) => answer(one.point)) }
        return answer(body?.pick?.point)
      }),
      put: vi.fn(async () => ({ conditions: {} })),
    },
  }
})

async function panel(onSave = vi.fn()) {
  render(<ConditionsPanel recipe={RECIPE} value={null} onSave={onSave} />)
  await waitFor(() => screen.getByText('면 찍기'))
  return onSave
}

/** 리본의 「조건 저장」 — 저장된 한 벌을 돌려준다. */
async function save(onSave: ReturnType<typeof vi.fn>) {
  fireEvent.click(screen.getByRole('button', { name: '조건 저장' }))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  return onSave.mock.calls[onSave.mock.calls.length - 1][0]
}

/** 3D 를 선택해 선택 그룹을 만든다 — 규칙(`rule`, 후보의 순번)을 바꿀 수도 있다. */
async function makeGroup(pick: string, name: string, rule?: string) {
  fireEvent.click(screen.getByText(pick))
  await waitFor(() => screen.getByRole('dialog', { name: '선택 그룹 추가' }))
  await waitFor(() => screen.getByLabelText('1번 선택 규칙'))
  if (rule) fireEvent.change(screen.getByLabelText('1번 선택 규칙'), { target: { value: rule } })
  fireEvent.change(screen.getByLabelText('그룹 이름'), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
}

test('선택하면 좌표가 아니라 **선택 규칙**으로 되돌려 주고, 그것이 선택 그룹이 된다', async () => {
  await panel()

  fireEvent.click(screen.getByText('면 찍기'))
  // 창 없이 3D 를 선택하면 「선택 그룹 추가」 창이 열린다.
  await waitFor(() => screen.getByRole('dialog', { name: '선택 그룹 추가' }))
  // 후보마다 「지금 몇 개에 맞나」 가 보여야 한다 — 하나만 집을지 부류 전부를 집을지 고른다.
  await waitFor(() => screen.getByRole('option', { name: 'bottom 면 (현재 1 개)' }))
  expect(screen.getByRole('option', { name: '이 자리의 면 (현재 1 개)' })).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('그룹 이름'), { target: { value: '바닥' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))

  // 트리에 생기고 펼쳐진다 — 셀렉터가 그대로 보인다(좌표가 아니라 「아래쪽 면」 이 저장된다).
  await waitFor(() => screen.getByText(/"role": "bottom"/))
  // 트리의 선택 그룹 줄 — 이름과 종류(face). 파트 「바닥판」 과 헷갈리지 않게 끝까지 맞춘다.
  expect(screen.getByRole('button', { name: /^바닥\s*face$/ })).toBeInTheDocument()
})

test('**Ctrl · Shift** 로 여럿을 한 그룹에 담고, 그 합으로 저장한다', async () => {
  const onSave = await panel()
  // 리본의 「선택 그룹」 으로 연다.
  fireEvent.click(screen.getByRole('button', { name: '선택 그룹' }))
  await waitFor(() => screen.getByRole('dialog', { name: '선택 그룹 추가' }))

  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByLabelText('1번 선택 규칙'))
  // Ctrl 은 더한다.
  fireEvent.click(screen.getByText('다른 면 찍기'), { ctrlKey: true })
  await waitFor(() => screen.getByLabelText('2번 선택 규칙'))
  // Shift 도 더한다 — 이미 담긴 것은 그대로.
  fireEvent.click(screen.getByText('면 찍기'), { shiftKey: true })
  expect(screen.queryByLabelText('3번 선택 규칙')).toBeNull()
  // Ctrl 로 담긴 것을 다시 누르면 뺀다.
  fireEvent.click(screen.getByText('면 찍기'), { ctrlKey: true })
  await waitFor(() => expect(screen.queryByLabelText('2번 선택 규칙')).toBeNull())
  // Shift 로 다시 더한다.
  fireEvent.click(screen.getByText('면 찍기'), { shiftKey: true })
  await waitFor(() => screen.getByLabelText('2번 선택 규칙'))
  // 3D 에 번호가 붙는다 — 목록의 몇 번이 어디인지.
  expect(lastMarks?.labels.map((one) => one.text)).toEqual(['1', '2'])

  fireEvent.change(screen.getByLabelText('그룹 이름'), { target: { value: '윗면과 바닥' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  // 트리가 「선택 규칙 2 개의 합」 이라고 말한다(숫자와 말만 그 줄의 제 글자다).
  await waitFor(() => screen.getByText(/^2 개의 합$/))

  const saved = await save(onSave)
  // **규칙 하나로는 이 모음을 말할 수 없다** — 고른 것마다의 규칙의 합이다.
  expect(saved.named_selections).toEqual([
    {
      name: '윗면과 바닥',
      entity: 'face',
      select: { any: [{ what: 'faces', role: 'top' }, { what: 'faces', role: 'bottom' }] },
    },
  ])
})

test('**Shift + 끌기**(사각형)로 고른 것들을 더하고, 규칙은 서버에 한 번에 묻는다', async () => {
  const calls = vi.mocked((await import('@/shared/api/client')).api.post)
  const onSave = await panel()
  // 하나를 먼저 고른 뒤 사각형으로 더한다 — 이미 담긴 것(아래 면)은 한 번만.
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByLabelText('1번 선택 규칙'))
  const before = calls.mock.calls.length

  fireEvent.click(screen.getByText('사각형 선택'))
  await waitFor(() => screen.getByLabelText('2번 선택 규칙'))
  expect(screen.queryByLabelText('3번 선택 규칙')).toBeNull()
  // 도면을 고른 수만큼 다시 만들지 않는다 — 묻는 것은 한 번, 새로 담을 것만.
  const asked = calls.mock.calls.slice(before).filter((one) => String(one[0]).includes('selectors'))
  expect(asked).toHaveLength(1)
  expect((asked[0][1] as { picks: unknown[] }).picks).toHaveLength(1)

  fireEvent.change(screen.getByLabelText('그룹 이름'), { target: { value: '위아래' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => screen.getByText(/^2 개의 합$/))
  expect((await save(onSave)).named_selections[0].select).toEqual({
    any: [{ what: 'faces', role: 'bottom' }, { what: 'faces', role: 'top' }],
  })
})

test('아무 키 없이 선택하면 **새로 고른다**', async () => {
  await panel()
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByRole('option', { name: 'bottom 면 (현재 1 개)' }))
  fireEvent.click(screen.getByText('다른 면 찍기'))
  await waitFor(() => screen.getByRole('option', { name: 'top 면 (현재 1 개)' }))
  expect(screen.queryByLabelText('2번 선택 규칙')).toBeNull()
})

test('리본에서 조건을 추가하면 **창**이 뜨고, 확인해야 한 벌에 들어간다', async () => {
  const onSave = await panel()
  await makeGroup('면 찍기', '바닥')
  await waitFor(() => screen.getByText(/"role": "bottom"/))

  // 도면 편집기와 같이 **더하는 것은 리본**이다.
  fireEvent.click(screen.getByRole('button', { name: '구속' }))
  await waitFor(() => screen.getByRole('dialog', { name: '구속 추가' }))
  // 첫 선택 그룹을 가리킨 채 생긴다 — 빈 칸으로 두면 저장에서 막힌다.
  fireEvent.click(screen.getByRole('button', { name: '확인' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

  const saved = await save(onSave)
  expect(saved.named_selections).toEqual([
    { name: '바닥', entity: 'face', select: { what: 'faces', role: 'bottom' } },
  ])
  expect(saved.constraints).toHaveLength(1)
  expect(saved.constraints[0].on).toBe('바닥')
  expect(saved.constraints[0].type).toBe('fixed_support')
})

test('창을 취소하면 아무것도 더해지지 않는다', async () => {
  const onSave = await panel()
  fireEvent.click(screen.getByRole('button', { name: '하중' }))
  await waitFor(() => screen.getByRole('dialog', { name: '하중 추가' }))
  fireEvent.click(screen.getByRole('button', { name: '취소' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

  expect((await save(onSave)).loads).toHaveLength(0)
})

test('꼭짓점을 선택하면 꼭짓점 그룹이 된다 — 점 · 엣지 · 면 · 바디를 모두 선택한다', async () => {
  const onSave = await panel()
  await makeGroup('점 찍기', '측정점')
  await waitFor(() => screen.getByText(/"role": "bottom"/))
  expect((await save(onSave)).named_selections[0].entity).toBe('vertex')
})

test('같은 이름을 두 번 사용하면 거절한다 — 조건이 어느 것을 가리킬지 알 수 없다', async () => {
  await panel()
  await makeGroup('면 찍기', '바닥')
  // 다른 규칙(「이 자리의 면」)에 같은 이름을 붙인다.
  await makeGroup('면 찍기', '바닥', '1')
  await waitFor(() => screen.getByText(/이미 있습니다/))
})

test('같은 자리를 다시 선택하면 **선택 그룹을 새로 만들지 않는다**', async () => {
  const onSave = await panel()
  await makeGroup('면 찍기', '바닥')
  await waitFor(() => screen.getByText(/"role": "bottom"/))

  // 조건마다 같은 면을 가리키는 일이 흔하다 — 그때마다 그룹이 늘면 목록을 못 읽는다.
  fireEvent.click(screen.getByRole('button', { name: '하중' }))
  await waitFor(() => screen.getByRole('dialog', { name: '하중 추가' }))
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByText(/「바닥」 이\(가\) 이미 있습니다/))
  fireEvent.click(screen.getByRole('button', { name: '적용 대상으로 지정' }))
  fireEvent.click(screen.getByRole('button', { name: '확인' }))

  const saved = await save(onSave)
  expect(saved.named_selections).toHaveLength(1)
  expect(saved.loads[0].on).toBe('바닥')
})

/** 리본의 「물성」 단추로 탐색기를 연다. */
async function openPicker() {
  fireEvent.click(screen.getByRole('button', { name: '물성' }))
  await waitFor(() => screen.getByRole('heading', { name: '물성 선택' }))
  await waitFor(() => screen.getByText('SPCC 1.2t'))
}

/** 트리에서 파트를 펼쳐 물성 하나를 지정한다. */
async function assign(part: string, material: string) {
  if (!screen.queryByRole('radiogroup', { name: `${part} 물성` })) {
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${part}`) }))
  }
  const group = await waitFor(() => screen.getByRole('radiogroup', { name: `${part} 물성` }))
  fireEvent.click(within(group).getByRole('radio', { name: material }))
}

test('물성은 MatNexus 에서 선택하여 **payload 전체**가 실린다', async () => {
  const onSave = await panel()

  await openPicker()
  // **줄을 누르면 담긴다** — 작은 확인란을 겨눌 필요가 없다.
  fireEvent.click(screen.getByText('SPCC 1.2t'))
  // 구조를 그대로 펼친다 — 우리가 아는 항목만 보여 주면 없는 줄 안다.
  await waitFor(() => screen.getByText(/22 °C/))
  fireEvent.click(screen.getByRole('button', { name: '물성 추가 (1)' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

  const saved = await save(onSave)
  expect(saved.materials).toHaveLength(1)
  expect(saved.materials[0].ref.code).toBe('M-000123')
  // **값을 해석하지 않는다** — 단위도 온도 표도 받은 그대로 실린다.
  expect(saved.materials[0].payload.declared_properties[0].si_unit).toBe('Pa')
  // 파트가 둘이라 **아직 어디에도 안 붙는다** — 어느 파트에 줄지는 사람이 트리에서 정한다.
  expect(saved.materials[0].apply_to).toEqual([])
})

test('여러 물성을 한 번에 담고, **트리에서 파트를 누르며** 지정한다', async () => {
  const onSave = await panel()

  await openPicker()
  fireEvent.click(screen.getByRole('checkbox', { name: '냉연강판 선택' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '알루미늄 6061 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '물성 추가 (2)' }))

  // 담자마자 **비어 있는 첫 파트**가 펼쳐진다 — 담아만 두고 잊지 않게.
  await waitFor(() => screen.getByRole('radiogroup', { name: '바닥판 물성' }))
  expect(screen.getByRole('button', { name: /^기둥/ })).toHaveTextContent('미지정')

  await assign('바닥판', 'SPCC 1.2t')
  // 3D 에서도 보인다 — 지정한 파트는 그 물성의 색, 남은 파트는 회색, 고른 파트만 또렷하게.
  await waitFor(() => expect(lastColors).toEqual({ 바닥판: 0x3b82f6, 기둥: 0x9ca3af }))
  expect(lastEmphasis).toBe('바닥판')

  await assign('기둥', 'AL6061-T6')
  await waitFor(() => expect(lastColors).toEqual({ 바닥판: 0x3b82f6, 기둥: 0x10b981 }))

  const saved = await save(onSave)
  expect(saved.materials.map((one: { apply_to: string[] }) => one.apply_to)).toEqual([['바닥판'], ['기둥']])
})

test('파트 하나에는 물성 하나 — 다른 물성을 고르면 먼저 것에서 빠진다', async () => {
  const onSave = await panel()
  await openPicker()
  fireEvent.click(screen.getByRole('checkbox', { name: '냉연강판 선택' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '알루미늄 6061 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '물성 추가 (2)' }))
  await waitFor(() => screen.getByRole('radiogroup', { name: '바닥판 물성' }))

  await assign('바닥판', 'SPCC 1.2t')
  await assign('기둥', 'SPCC 1.2t')
  // 같은 재료를 두 파트에 — **한 번만 담고** 두 파트가 가리킨다(덱 번호도 하나다).
  await assign('바닥판', 'AL6061-T6')

  const saved = await save(onSave)
  // 둘이 한 파트를 가리키면 해석 쪽이 어느 것으로 풀지 모른다 — 서버도 막는 규칙이다.
  expect(saved.materials.map((one: { apply_to: string[] }) => one.apply_to)).toEqual([['기둥'], ['바닥판']])
})

test('선택 대상을 지정하면 **그 종류만** 선택된다', async () => {
  await panel()
  // 작은 것에서 큰 것으로 — 점 · 엣지 · 면 · 바디.
  expect(
    screen.getAllByRole('button', { name: /^(점|엣지|면|바디)$/ }).map((one) => one.textContent),
  ).toEqual(['점', '엣지', '면', '바디'])
  // 기본은 면 — 조건이 가장 많이 붙는 자리다.
  expect(lastKinds).toEqual({ point: false, edge: false, face: true, body: false })

  // **엣지를 고르려는데 점이 먼저 잡히던 것**이 이 거르개가 없어서였다.
  fireEvent.click(screen.getByRole('button', { name: '엣지' }))
  await waitFor(() => expect(lastKinds).toEqual({ point: false, edge: true, face: false, body: false }))

  // 바디는 면을 눌러 고르므로 면과 함께 켜면 안 된다 — 하나씩만 켜는 것이 그 문제도 푼다.
  fireEvent.click(screen.getByRole('button', { name: '바디' }))
  await waitFor(() => expect(lastKinds).toEqual({ point: false, edge: false, face: false, body: true }))
})

test('바디는 서버에 조회하지 않는다 — 이름이 곧 답이다', async () => {
  const calls = vi.mocked((await import('@/shared/api/client')).api.post)
  await panel()
  fireEvent.click(screen.getByRole('button', { name: '바디' }))
  const before = calls.mock.calls.length

  fireEvent.click(screen.getByText('바디 찍기'))
  await waitFor(() => screen.getByRole('option', { name: /바디 「기둥」/ }))
  // 면 · 엣지 · 점은 「이 자리를 무엇으로 부를까」 를 서버에 되묻지만, 바디는 그럴 것이 없다.
  expect(
    calls.mock.calls.slice(before).filter((one) => String(one[0]).includes('selectors')),
  ).toHaveLength(0)

  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => screen.getByText(/"body": "기둥"/))
})

test('조건 창은 **3D 를 가리지 않는다** — 띄운 채 3D 를 선택한다', async () => {
  await panel()
  fireEvent.click(screen.getByRole('button', { name: '구속' }))
  await waitFor(() => screen.getByRole('dialog', { name: '구속 추가' }))

  // 막으로 덮는 모달이면 뒤가 가려져(aria-hidden) 3D 를 누를 수 없다 — 열고 닫기를
  // 되풀이하게 된다. 측정 창과 같이 **막 없는 창**이다.
  expect(screen.getByText('면 찍기')).toBeInTheDocument()
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => within(screen.getByRole('dialog', { name: '구속 추가' })).getByLabelText('1번 선택 규칙'))
})

test('조건 창을 띄운 채 형상을 선택하면 **그 조건의 적용 대상**이 된다', async () => {
  const onSave = await panel()
  fireEvent.click(screen.getByRole('button', { name: '구속' }))
  await waitFor(() => screen.getByRole('dialog', { name: '구속 추가' }))

  // 그룹을 따로 만들고 조건으로 돌아가 목록에서 고르면 한 가지 일이 세 걸음이 된다.
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByLabelText('1번 선택 규칙'))
  fireEvent.change(screen.getByLabelText('그룹 이름'), { target: { value: '바닥' } })
  fireEvent.click(screen.getByRole('button', { name: '적용 대상으로 지정' }))

  // 창은 그대로 — 방금 지정한 결과를 그 자리에서 확인한다.
  await waitFor(() => expect(screen.queryByLabelText('1번 선택 규칙')).toBeNull())
  expect(screen.getByRole('dialog', { name: '구속 추가' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '확인' }))

  expect((await save(onSave)).constraints[0].on).toBe('바닥')
})

test('트리의 조건을 누르면 **수정 창**이 뜨고, 거기서 삭제한다', async () => {
  const onSave = await panel()
  fireEvent.click(screen.getByRole('button', { name: '하중' }))
  await waitFor(() => screen.getByRole('dialog', { name: '하중 추가' }))
  fireEvent.click(screen.getByRole('button', { name: '확인' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

  // 가지 머리(「하중 1」)가 아니라 조건 줄 — 대상이 아직 없어 「대상 미지정」 이 붙는다.
  fireEvent.click(screen.getByRole('button', { name: /^하중 1\s*대상 미지정$/ }))
  await waitFor(() => screen.getByRole('dialog', { name: '하중 수정' }))
  fireEvent.click(screen.getByRole('button', { name: '삭제' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

  expect((await save(onSave)).loads).toHaveLength(0)
})

test('초기조건은 **바디만** 가리킨다', async () => {
  const onSave = await panel()

  // 면 그룹 하나와 바디 그룹 하나를 만든다.
  await makeGroup('면 찍기', '바닥면')
  await waitFor(() => screen.getByText(/"role": "bottom"/))
  fireEvent.click(screen.getByRole('button', { name: '바디' }))
  await makeGroup('바디 찍기', '기둥몸')
  await waitFor(() => screen.getByText(/"body": "기둥"/))
  fireEvent.click(screen.getByRole('button', { name: '면' }))

  // **온도 · 속도 · 예응력은 몸 전체의 상태다** — 한 면에 걸 수 없다. 면 그룹을 고를 수
  // 있게 두면 해석 쪽에서야 「그 자리에 못 건다」 를 안다.
  // **바디 그룹이 기본으로 지정된다** — 면 그룹을 먼저 만들었는데도.
  fireEvent.click(screen.getByRole('button', { name: '초기조건' }))
  await waitFor(() => screen.getByRole('dialog', { name: '초기조건 추가' }))
  // 창이 떠 있는 동안 선택 대상은 바디뿐이다.
  expect(screen.getByRole('button', { name: '면' })).toBeDisabled()
  expect(lastKinds).toEqual({ point: false, edge: false, face: false, body: true })
  fireEvent.click(screen.getByRole('button', { name: '확인' }))
  // 닫으면 원래 선택 대상(면)으로 돌아간다.
  await waitFor(() => expect(lastKinds).toEqual({ point: false, edge: false, face: true, body: false }))

  expect((await save(onSave)).initial[0].on).toBe('기둥몸')
})

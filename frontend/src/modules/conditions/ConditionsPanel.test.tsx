import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ConditionsPanel } from '@/modules/conditions/ConditionsPanel'

/** 3D 대신 단추 셋 — 면 · 엣지 · 점을 찍는 것만 흉내 낸다. */
/** 뷰어가 받은 거르개 — 「켠 것 하나만」 을 시험이 볼 수 있게 내놓는다. */
let lastKinds: Record<string, boolean> | undefined
vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({
    onMeasure,
    measureKinds,
  }: {
    onMeasure?: (pick: unknown) => void
    measureKinds?: Record<string, boolean>
  }) => {
    lastKinds = measureKinds
    return (
      <div>
        <button onClick={() => onMeasure?.({ kind: 'face', face: { center: [0, 0, 0] } })}>
          면 찍기
        </button>
        <button onClick={() => onMeasure?.({ kind: 'point', at: [1, 2, 3] })}>점 찍기</button>
        <button onClick={() => onMeasure?.({ kind: 'body', name: '기둥' })}>바디 찍기</button>
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
      post: vi.fn(async (path: string) => (path.startsWith('/cad/recipe/bodies') ? BODIES : CANDIDATES)),
      put: vi.fn(async () => ({ conditions: {} })),
    },
  }
})

async function panel(onSave = vi.fn()) {
  render(<ConditionsPanel recipe={RECIPE} value={null} onSave={onSave} />)
  await waitFor(() => screen.getByText('면 찍기'))
  return onSave
}

test('선택하면 좌표가 아니라 **선택 규칙**으로 되돌려 주고, 그것이 이름표가 된다', async () => {
  await panel()

  fireEvent.click(screen.getByText('면 찍기'))
  // 후보마다 「지금 몇 개에 맞나」 가 보여야 한다 — 하나만 집을지 부류 전부를 집을지 고른다.
  await waitFor(() => screen.getByText('bottom 면'))
  expect(screen.getAllByText(/현재 1 개/)).toHaveLength(2)

  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '바닥' } })
  fireEvent.click(screen.getByText('이름표 생성'))

  // 왼쪽 목록과 오른쪽 속성 양쪽에 뜬다 — 고른 것이 무엇인지 두 자리에서 보인다.
  await waitFor(() => expect(screen.getAllByText('바닥').length).toBeGreaterThan(0))
  // 셀렉터가 그대로 보인다 — 좌표가 아니라 「아래쪽 면」 이라는 말이 저장된다.
  expect(screen.getByText(/"role": "bottom"/)).toBeTruthy()
})

test('조건은 이름표를 가리키고, 저장하면 그 한 벌이 그대로 올라간다', async () => {
  const onSave = await panel()

  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByText('bottom 면'))
  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '바닥' } })
  fireEvent.click(screen.getByText('이름표 생성'))
  await waitFor(() => expect(screen.getAllByText('바닥').length).toBeGreaterThan(0))

  // 구속을 더하면 **첫 이름표를 가리킨 채** 생긴다 — 빈 칸으로 두면 저장에서 막힌다.
  fireEvent.click(screen.getByRole('button', { name: '구속 추가' }))
  await waitFor(() => screen.getByLabelText('이름'))

  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  const saved = onSave.mock.calls[0][0]
  expect(saved.named_selections).toEqual([
    { name: '바닥', entity: 'face', select: { what: 'faces', role: 'bottom' } },
  ])
  expect(saved.constraints).toHaveLength(1)
  expect(saved.constraints[0].on).toBe('바닥')
  expect(saved.constraints[0].type).toBe('fixed_support')
})

test('꼭짓점을 선택하면 꼭짓점 이름표가 된다 — 면 · 엣지 · 꼭짓점을 모두 선택한다', async () => {
  const onSave = await panel()

  fireEvent.click(screen.getByText('점 찍기'))
  await waitFor(() => screen.getByText('bottom 면')) // 가짜 서버가 같은 후보를 준다
  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '측정점' } })
  fireEvent.click(screen.getByText('이름표 생성'))

  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  expect(onSave.mock.calls[0][0].named_selections[0].entity).toBe('vertex')
})

test('같은 이름을 두 번 사용하면 거절한다 — 조건이 어느 것을 가리킬지 알 수 없다', async () => {
  await panel()

  for (const name of ['바닥', '바닥']) {
    fireEvent.click(screen.getByText('면 찍기'))
    await waitFor(() => screen.getByText('bottom 면'))
    fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: name } })
    fireEvent.click(screen.getByText('이름표 생성'))
  }
  await waitFor(() => screen.getByText(/이미 있습니다/))
})

test('물성은 MatNexus 에서 선택하여 **payload 전체**가 실린다', async () => {
  const onSave = await panel()

  fireEvent.click(screen.getByRole('button', { name: '물성 추가' }))
  await waitFor(() => screen.getByText('물성 고르기'))
  await waitFor(() => screen.getByText('SPCC 1.2t'))

  fireEvent.click(screen.getByText('SPCC 1.2t'))
  // 구조를 그대로 펼친다 — 우리가 아는 항목만 보여 주면 없는 줄 안다.
  await waitFor(() => screen.getByText(/22 °C/))
  fireEvent.click(screen.getByText('물성 적용'))

  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  const saved = onSave.mock.calls[0][0]
  expect(saved.materials).toHaveLength(1)
  expect(saved.materials[0].ref.code).toBe('M-000123')
  // **값을 해석하지 않는다** — 단위도 온도 표도 받은 그대로 실린다.
  expect(saved.materials[0].payload.declared_properties[0].si_unit).toBe('Pa')
})

test('물성을 **어느 바디에** 적용할지 선택한다', async () => {
  const onSave = await panel()

  fireEvent.click(screen.getByRole('button', { name: '물성 추가' }))
  await waitFor(() => screen.getByText('물성 고르기'))
  await waitFor(() => screen.getByText('SPCC 1.2t'))
  fireEvent.click(screen.getByText('SPCC 1.2t'))
  fireEvent.click(screen.getByText('물성 적용'))

  // **대화상자가 아니라 옆 패널이다** — 3D 를 보면서 바디를 골라야 하므로 뒤를 가리면 안 된다.
  await waitFor(() => screen.getByText('적용 대상'))
  // 「전체」 는 목록 맨 위와 왼쪽 배지 양쪽에 나온다 — 누를 수 있는 것으로 좁힌다.
  const 자리 = screen.getAllByRole('button', { name: /전체/ })
  expect(자리.some((one) => one.getAttribute('aria-pressed') === 'true')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: /기둥/ }))

  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  // **이것이 없으면 조립을 훑어도 물성이 늘 「전체」** 라, 판과 기둥에 다른 재료를 못 준다.
  expect(onSave.mock.calls[0][0].materials[0].apply_to).toBe('기둥')
})

test('선택 대상을 지정하면 **그 종류만** 선택된다', async () => {
  await panel()
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
  await waitFor(() => screen.getByText(/바디 「기둥」/))
  // 면 · 엣지 · 점은 「이 자리를 무엇으로 부를까」 를 서버에 되묻지만, 바디는 그럴 것이 없다.
  expect(
    calls.mock.calls.slice(before).filter((one) => String(one[0]).includes('selectors')),
  ).toHaveLength(0)

  fireEvent.click(screen.getByText('이름표 생성'))
  await waitFor(() => screen.getByRole('button', { name: /기둥/ }))
})

test('조건을 추가하면 **옆 패널**에서 바로 수정한다 — 3D 를 가리지 않는다', async () => {
  await panel()
  fireEvent.click(screen.getByRole('button', { name: '구속 추가' }))
  await waitFor(() => screen.getByText('구속 수정'))

  // **대화상자를 쓰지 않는다.** 조건이 해당하는 형상을 3D 에서 선택해야 하는데, 모달이
  // 뒤를 가리면 그 선택을 할 수 없어 열고 닫기를 되풀이하게 된다.
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.getByText('면 찍기')).toBeInTheDocument()
})

test('조건을 수정하는 중에 형상을 선택하면 **그 조건의 적용 대상**이 된다', async () => {
  const onSave = await panel()
  fireEvent.click(screen.getByRole('button', { name: '구속 추가' }))
  await waitFor(() => screen.getByText('구속 수정'))

  // 이름표를 따로 만들고 조건으로 돌아가 목록에서 고르면 한 가지 일이 세 걸음이 된다.
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByText('bottom 면'))
  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '바닥' } })
  fireEvent.click(screen.getByText('이름표 생성'))

  // 수정하던 자리에 머문다 — 방금 지정한 결과를 그 자리에서 확인한다.
  await waitFor(() => screen.getByText('구속 수정'))
  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  expect(onSave.mock.calls[0][0].constraints[0].on).toBe('바닥')
})

test('초기조건은 **바디만** 가리킨다', async () => {
  const onSave = await panel()

  // 면 이름표 하나와 바디 이름표 하나를 만든다.
  fireEvent.click(screen.getByText('면 찍기'))
  await waitFor(() => screen.getByText('bottom 면'))
  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '바닥면' } })
  fireEvent.click(screen.getByText('이름표 생성'))

  fireEvent.click(screen.getByRole('button', { name: '바디' }))
  fireEvent.click(screen.getByText('바디 찍기'))
  await waitFor(() => screen.getByText(/바디 「기둥」/))
  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '기둥몸' } })
  fireEvent.click(screen.getByText('이름표 생성'))

  // **온도 · 속도 · 예응력은 몸 전체의 상태다** — 한 면에 걸 수 없다. 면 이름표를 고를 수
  // 있게 두면 해석 쪽에서야 「그 자리에 못 건다」 를 안다.
  // **바디 이름표가 기본으로 지정된다** — 면 이름표를 먼저 만들었는데도.
  fireEvent.click(screen.getByRole('button', { name: '초기조건 추가' }))
  await waitFor(() => screen.getByText('초기조건 수정'))
  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  expect(onSave.mock.calls[0][0].initial[0].on).toBe('기둥몸')
})

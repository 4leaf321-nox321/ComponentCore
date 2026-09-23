import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ConditionsPanel } from '@/modules/conditions/ConditionsPanel'

/** 3D 대신 단추 셋 — 면 · 엣지 · 점을 찍는 것만 흉내 낸다. */
vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({ onMeasure }: { onMeasure?: (pick: unknown) => void }) => (
    <div>
      <button onClick={() => onMeasure?.({ kind: 'face', face: { center: [0, 0, 0] } })}>
        면 찍기
      </button>
      <button onClick={() => onMeasure?.({ kind: 'point', at: [1, 2, 3] })}>점 찍기</button>
    </div>
  ),
}))
vi.mock('@/modules/cad/useRecipeMesh', () => ({
  useRecipeMesh: () => ({ mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] }, problems: [] }),
}))

const SCHEMA = {
  schema_version: 1,
  units: { length: 'mm' },
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

vi.mock('@/shared/api/client', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@/shared/api/client')
  return {
    ...actual,
    api: {
      get: vi.fn(async () => SCHEMA),
      post: vi.fn(async () => CANDIDATES),
      put: vi.fn(async () => ({ conditions: {} })),
    },
  }
})

async function panel(onSave = vi.fn()) {
  render(<ConditionsPanel recipe={RECIPE} value={null} onSave={onSave} />)
  await waitFor(() => screen.getByText('면 찍기'))
  return onSave
}

test('찍으면 좌표가 아니라 **말**로 되돌려 주고, 고른 것이 이름표가 된다', async () => {
  await panel()

  fireEvent.click(screen.getByText('면 찍기'))
  // 후보마다 「지금 몇 개에 맞나」 가 보여야 한다 — 하나만 집을지 부류 전부를 집을지 고른다.
  await waitFor(() => screen.getByText('bottom 면'))
  expect(screen.getAllByText(/지금 1개/)).toHaveLength(2)

  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '바닥' } })
  fireEvent.click(screen.getByText('이름표 만들기'))

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
  fireEvent.click(screen.getByText('이름표 만들기'))
  await waitFor(() => expect(screen.getAllByText('바닥').length).toBeGreaterThan(0))

  // 구속을 더하면 **첫 이름표를 가리킨 채** 생긴다 — 빈 칸으로 두면 저장에서 막힌다.
  const plus = screen.getAllByRole('button', { name: '+' })
  fireEvent.click(plus[0])
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

test('점을 찍으면 점 이름표가 된다 — 면 · 엣지 · 점을 모두 고른다', async () => {
  const onSave = await panel()

  fireEvent.click(screen.getByText('점 찍기'))
  await waitFor(() => screen.getByText('bottom 면')) // 가짜 서버가 같은 후보를 준다
  fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: '측정점' } })
  fireEvent.click(screen.getByText('이름표 만들기'))

  fireEvent.click(screen.getByText('조건 저장'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  expect(onSave.mock.calls[0][0].named_selections[0].entity).toBe('vertex')
})

test('같은 이름을 두 번 쓰면 막는다 — 조건이 어느 것을 가리킬지 알 수 없다', async () => {
  await panel()

  for (const name of ['바닥', '바닥']) {
    fireEvent.click(screen.getByText('면 찍기'))
    await waitFor(() => screen.getByText('bottom 면'))
    fireEvent.change(screen.getByLabelText('이름표 이름'), { target: { value: name } })
    fireEvent.click(screen.getByText('이름표 만들기'))
  }
  await waitFor(() => screen.getByText(/이미 있습니다/))
})

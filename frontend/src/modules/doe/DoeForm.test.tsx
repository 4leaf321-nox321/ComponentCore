import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Recipe } from '@/modules/cad/api'
import { DoeForm } from '@/modules/doe/DoeForm'

const RECIPE: Recipe = {
  params: { 두께: 6, 길이: 90 },
  nodes: [{ id: 'b', op: 'box', length: '=길이', width: 40, height: '=두께' }],
}

function mockApi(count = 10) {
  const calls: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url, body })
    const payload = url.endsWith('/doe/preview')
      ? { count, max: 200, max_samples: 500, too_many: count > 200, points: [], varying: ['두께'] }
      : { id: 'study-1' }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

test('변수에 범위를 주면 설계점 개수를 먼저 보여 준다', async () => {
  const calls = mockApi(10)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  // 처음에는 모두 고정 — 바꿀 변수를 고르라고 한다.
  expect(screen.getByText(/변경할 변수를 하나 이상/)).toBeInTheDocument()

  // [0] 두께 행의 방식 · [1] 길이 행 · [2] 방법
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8, 12' } })

  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe/preview'))).toBe(true))
  await waitFor(() => expect(screen.getByText('10')).toBeInTheDocument())
})

test('설계점이 너무 많으면 만들지 못하게 막는다', async () => {
  mockApi(625)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '1,2,3' } })
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '훑기' } })
  await waitFor(() => expect(screen.getByText(/최대 200개까지 생성할 수 있습니다/)).toBeInTheDocument())
  expect(screen.getByRole('button', { name: '생성' })).toBeDisabled()
})

test('변수가 없으면 어디서 어떻게 만드는지 알려 주고, 편집기로 보내 준다', () => {
  const onEditRecipe = vi.fn()
  render(<DoeForm recipe={{ nodes: [] }} onCreated={() => {}} onEditRecipe={onEditRecipe} />)
  expect(screen.getByText(/먼저 도면에 ‘변수’를 생성해야 합니다/)).toBeInTheDocument()
  expect(screen.getByText(/fx/)).toBeInTheDocument() // 어느 단추를 누르는지까지
  fireEvent.click(screen.getByRole('button', { name: '도면 수정' }))
  expect(onEditRecipe).toHaveBeenCalled()
})

test('「구간」 으로 바꾸고 칸을 손대지 않아도 시작 · 끝 · 단계가 채워져 서버로 간다', async () => {
  const calls = mockApi(5)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '구간' }))
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: 'test1' } })
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe/preview'))).toBe(true))
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe/studies') || c.url.endsWith('/doe'))).toBe(true))
  const made = calls.find((c) => c.url.endsWith('/doe/studies') || c.url.endsWith('/doe'))!.body as { factors: { name: string; mode: string; start?: number; end?: number; steps?: number }[] }
  // 손대지 않은 구간은 지금 값에서 시작해 두 배까지 5단계 — 빈 채로 보내지 않는다.
  expect(made.factors.find((f) => f.name === '두께')).toMatchObject({ mode: 'range', start: 6, end: 12, steps: 5 })
  // 재료는 보내지 않는다 — 표에는 바꾼 변수만 적힌다.
  expect('material' in (made as object)).toBe(false)
})

test('구간 값은 가공 단위로 맞춰 보여 준다 — 0.333 은 나오지 않는다', async () => {
  mockApi(4)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '구간' }))
  fireEvent.change(screen.getByLabelText('두께 끝'), { target: { value: '7' } })
  fireEvent.change(screen.getByLabelText('두께 단계'), { target: { value: '4' } })
  expect(screen.getByText('6 · 6.3 · 6.7 · 7')).toBeInTheDocument()
  // 0.5 단위로 바꾸면 넷이 셋으로 준다.
  fireEvent.click(screen.getByRole('combobox', { name: '두께 가공 단위' }))
  fireEvent.click(await screen.findByRole('option', { name: '0.5 mm' }))
  expect(screen.getByText('6 · 6.5 · 7')).toBeInTheDocument()
})

test('숫자 칸은 다 지울 수 있고, 비어 있으면 만들기가 막힌다', async () => {
  const calls = mockApi(5)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '구간' }))
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '훑기' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).toBeEnabled())
  const before = calls.filter((c) => c.url.endsWith('/doe/preview')).length

  // 단계를 다 지운다 — 1 로 되돌리지 않고 빈 채로 둔다. 서버에 묻지 않고 만들기가 막힌다.
  fireEvent.change(screen.getByLabelText('두께 단계'), { target: { value: '' } })
  expect(screen.getByLabelText('두께 단계')).toHaveValue(null)
  expect(screen.getByRole('button', { name: '생성' })).toBeDisabled()
  expect(screen.getByText('빈 입력란을 채우면 설계점 수를 계산합니다.')).toBeInTheDocument()
  await new Promise((r) => setTimeout(r, 50))
  expect(calls.filter((c) => c.url.endsWith('/doe/preview'))).toHaveLength(before)

  // 처음부터 친다 — 3.
  fireEvent.change(screen.getByLabelText('두께 단계'), { target: { value: '3' } })
  expect(screen.getByLabelText('두께 단계')).toHaveValue(3)
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).toBeEnabled())
})

test('담아 둔 재료를 바디마다 후보로 고르면 **재료 인자**로 서버에 간다 — 조건은 서버가 싣는다', async () => {
  const calls: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url, body })
    const payload = url.endsWith('/cad/recipe/bodies')
      ? { items: [{ name: '받침판' }, { name: '블록' }] }
      : url.endsWith('/doe/preview')
        ? { count: 2, max: 200, max_samples: 500, too_many: false, points: [], varying: ['재료 · 블록'] }
        : { id: 'study-1' }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const conditions = {
    materials: [
      { apply_to: ['받침판'], ref: { name: 'SECC', code: 'M-1' }, payload: {} },
      { apply_to: ['블록'], ref: { name: 'AL5052', code: 'M-2' }, payload: {} },
    ],
  }
  const onCreated = vi.fn()
  render(<DoeForm recipe={RECIPE} conditions={conditions} workId="w-1" onCreated={onCreated} />)
  await waitFor(() => screen.getByText('블록'))
  expect(screen.getByText('현재: AL5052')).toBeInTheDocument()
  expect(screen.getByText(/시뮬레이션 조건\(구속, 하중, 접촉, 물성, 해석 설정\)이 함께 포함되어/)).toBeInTheDocument()
  expect(screen.getByText(/저장하지 않은 내용은 포함되지 않습니다/)).toBeInTheDocument()

  // 재료만 훑어도 된다 — 치수는 모두 고정.
  fireEvent.click(screen.getByLabelText('블록 후보 AL5052'))
  fireEvent.click(screen.getByLabelText('블록 후보 SECC'))
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '재료 훑기' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith('study-1'))

  const created = calls.find((c) => c.url.endsWith('/doe'))!.body as { factors: unknown[]; conditions?: unknown }
  expect(created.factors).toContainEqual({ name: '재료 · 블록', mode: 'material', bodies: ['블록'], values: ['AL5052', 'SECC'] })
  // 작업이 있으면 조건을 싣지 않는다 — 서버가 그 작업의 현재 조건을 싣는다.
  expect(created.conditions).toBeUndefined()
})

test('**조건 바꿔 보기**와 **물성 배율**이 고르기 · 배율 인자로 서버에 간다', async () => {
  const calls: { url: string; body: unknown }[] = []
  const schema = {
    unit_systems: [],
    entities: [],
    analysis: { properties: { type: { enum: ['modal', 'static'] } } },
    groups: {
      contacts: {
        label: '접촉',
        types: ['bonded', 'frictional'],
        fields: { name: {}, type: { enum: ['bonded', 'frictional'], labels: { bonded: '본딩', frictional: '마찰' } } },
        required: [],
      },
    },
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url, body })
    const payload = url.endsWith('/cad/recipe/bodies')
      ? { items: [{ name: '블록' }] }
      : url.endsWith('/cad/conditions/schema')
        ? schema
        : url.endsWith('/doe/preview')
          ? { count: 4, max: 200, max_samples: 500, too_many: false, points: [], varying: [] }
          : { id: 'study-1' }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const conditions = {
    contacts: [{ name: '블록-판', type: 'bonded', source: 'a', target: 'b' }],
    materials: [{ apply_to: ['블록'], ref: { name: 'AL5052' }, payload: { declared_properties: [{ item: '탄성계수' }] } }],
  }
  const onCreated = vi.fn()
  render(<DoeForm recipe={RECIPE} conditions={conditions} workId="w-1" onCreated={onCreated} />)

  // 조건의 고르는 칸을 더하고 후보를 고른다.
  const add = await screen.findByLabelText('변경할 필드 추가')
  await waitFor(() => expect(add.querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(add, { target: { value: 'contacts|블록-판|type' } })
  fireEvent.click(screen.getByLabelText('접촉 「블록-판」 · 종류 후보 본딩'))
  fireEvent.click(screen.getByLabelText('접촉 「블록-판」 · 종류 후보 마찰'))
  // 블록 탄성계수에 배율.
  fireEvent.change(await screen.findByLabelText('블록 배율 물성'), { target: { value: '탄성계수' } })
  fireEvent.change(screen.getByLabelText('블록 배율 값'), { target: { value: '0.9, 1.1' } })

  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '조건 훑기' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(onCreated).toHaveBeenCalled())
  const created = calls.find((c) => c.url.endsWith('/doe'))!.body as { factors: unknown[] }
  expect(created.factors).toContainEqual({
    name: '접촉 「블록-판」 · 종류',
    mode: 'choice',
    target: { group: 'contacts', item: '블록-판', field: 'type' },
    values: ['bonded', 'frictional'],
  })
  expect(created.factors).toContainEqual({ name: '탄성계수 배율 · 블록', mode: 'scale', bodies: ['블록'], property: '탄성계수', values: [0.9, 1.1] })
})

test('제약식을 적으면 미리보기가 거른 수와 제약마다 걸린 수를 보여 주고, 만들 때 함께 보낸다', async () => {
  const calls: { url: string; body: Record<string, unknown> | null }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url, body })
    const filtered = Array.isArray(body?.constraints) && body.constraints.length > 0
    const payload = url.endsWith('/doe/preview')
      ? { count: filtered ? 4 : 6, requested: 6, max: 200, max_samples: 500, too_many: false, points: [], varying: ['두께'], rejected: filtered ? 2 : 0, candidates: 6, hits: filtered ? [2] : [], shortfall: 0 }
      : { id: 'study-1' }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const onCreated = vi.fn()
  render(<DoeForm recipe={RECIPE} onCreated={onCreated} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8, 12' } })
  fireEvent.click(screen.getByRole('button', { name: '+ 제약 추가' }))
  fireEvent.change(screen.getByLabelText('제약 1'), { target: { value: '길이 >= 10 * 두께' } })

  await waitFor(() => expect(screen.getByText(/후보 6개 중 2개가 제약 조건으로 제외되었습니다/)).toBeInTheDocument())
  expect(screen.getByText('2개 위반')).toBeInTheDocument()
  const asked = calls.filter((c) => c.url.endsWith('/doe/preview')).at(-1)!.body!
  expect(asked.constraints).toEqual(['길이 >= 10 * 두께'])
  expect(asked.recipe).toEqual(RECIPE)

  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '제약 훑기' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith('study-1'))
  const made = calls.find((c) => c.url.endsWith('/doe') && c.body?.name === '제약 훑기')!.body!
  expect(made.constraints).toEqual(['길이 >= 10 * 두께'])
})

test('끝 점을 미리 만들어 보면 실패 · 건너뜀 · 그룹 어긋남과 걸릴 시간을 보여 준다', async () => {
  const calls: { url: string; body: Record<string, unknown> | null }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url, body })
    const payload = url.endsWith('/doe/preview')
      ? { count: 120, max: 200, max_samples: 500, too_many: false, points: [], varying: ['두께'] }
      : url.endsWith('/doe/probe')
        ? {
            mean_ms: 2000,
            setup_ms: 0,
            regions: ['고정면'],
            points: [
              { label: '가운데', params: { 두께: 8 }, status: 'ok', error: '', ms: 2000, unresolved: [], drift: [], interference: null, solids: 1, faces: 10, warnings: [] },
              { label: '‘두께’ 최소', params: { 두께: 0 }, status: 'failed', error: '높이가 0 입니다', ms: 5 },
              { label: '‘두께’ 최대', params: { 두께: 12 }, status: 'ok', error: '', ms: 2000, unresolved: ['고정면'], drift: [{ name: '하중면', distance: 3.5 }], interference: null, solids: 2, faces: 12, warnings: [] },
            ],
          }
        : {}
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<DoeForm recipe={RECIPE} workId="w1" onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '0, 8, 12' } })
  await waitFor(() => expect(screen.getByText('120')).toBeInTheDocument())

  fireEvent.click(screen.getByRole('button', { name: '경계점 사전 생성' }))
  expect(await screen.findByText(/2개에 문제가 있습니다/)).toBeInTheDocument()
  expect(screen.getByText(/실패: 높이가 0 입니다/)).toBeInTheDocument()
  expect(screen.getByText(/찾지 못한 그룹: 고정면/)).toBeInTheDocument()
  expect(screen.getByText(/하중면: 예측 위치에서 3.50 mm 벗어남/)).toBeInTheDocument()
  expect(screen.getByText(/바디 수 1 → 2/)).toBeInTheDocument()
  // 한 점 2초 × 120점 = 4분.
  expect(screen.getByText(/전체 120개 기준 약 4분/)).toBeInTheDocument()
  const asked = calls.find((c) => c.url.endsWith('/doe/probe'))!.body!
  expect(asked.work_id).toBe('w1')

  // 설정을 바꾸면 옛 결과라고 말한다.
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '2, 8, 12' } })
  expect(await screen.findByText(/설정이 변경되었습니다/)).toBeInTheDocument()
})

test('형상 점검 기준은 바꾼 것만 보낸다', async () => {
  const calls = mockApi(3)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8, 12' } })
  fireEvent.change(screen.getByLabelText('최소 벽 두께 기준'), { target: { value: '1.5' } })
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '점검' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe'))).toBe(true))
  const made = calls.find((c) => c.url.endsWith('/doe'))!.body as Record<string, unknown>
  expect(made.checks).toEqual({ min_wall: 1.5 })
})

test('표 직접 넣기 — 붙여 넣은 표를 줄 그대로 보내고, 표에 없는 변수는 고정이다', async () => {
  const calls = mockApi(2)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getByLabelText('방법'))
  fireEvent.click(await screen.findByRole('option', { name: '표 직접 입력 (CSV)' }))
  expect(screen.getByText(/설계점 표를 붙여 넣거나/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('설계점 표 (CSV)'), { target: { value: 'point\t두께\n1\t6.333\n2\t4\n' } })
  expect(screen.getByText(/2행, 열: 두께/)).toBeInTheDocument()
  expect(screen.getByText('표의 값')).toBeInTheDocument()

  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe/preview'))).toBe(true))
  const asked = calls.filter((c) => c.url.endsWith('/doe/preview')).at(-1)!.body as Record<string, unknown>
  expect(asked.method).toBe('table')
  expect(asked.table).toEqual([{ 두께: '6.333' }, { 두께: '4' }])
  expect(asked.factors).toEqual([
    { name: '두께', mode: 'fixed', value: 6 },
    { name: '길이', mode: 'fixed', value: 90 },
  ])

  // 도면에 없는 열은 미리 말한다.
  fireEvent.change(screen.getByLabelText('설계점 표 (CSV)'), { target: { value: '높이\n3\n' } })
  expect(screen.getByText('도면에 없는 변수: 높이')).toBeInTheDocument()
})

test('측정값 — 종류를 고르면 이름이 붙고, 선택 그룹은 조건의 것에서 고르며, 만들 때 함께 보낸다', async () => {
  const calls = mockApi(3)
  const conditions = { named_selections: [{ name: '바닥', entity: 'face', select: {} }, { name: '블록', entity: 'body', select: {} }] }
  render(<DoeForm recipe={RECIPE} conditions={conditions} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8, 12' } })

  fireEvent.change(screen.getByLabelText('측정값 추가'), { target: { value: 'volume' } })
  fireEvent.change(screen.getByLabelText('측정값 추가'), { target: { value: 'region_area' } })
  fireEvent.change(screen.getByLabelText('측정값 추가'), { target: { value: 'expr' } })
  expect(screen.getByLabelText('측정값 1 이름')).toHaveValue('부피')
  // 바디 그룹은 넓이를 잴 수 없다 — 면 그룹만 고른다.
  const group = screen.getByLabelText('측정값 2 그룹')
  expect([...group.querySelectorAll('option')].map((one) => one.textContent)).toEqual(['그룹 선택', '바닥'])
  fireEvent.change(group, { target: { value: '바닥' } })
  fireEvent.change(screen.getByLabelText('측정값 3 식'), { target: { value: '부피 * 7.85e-6' } })
  fireEvent.change(screen.getByLabelText('측정값 3 이름'), { target: { value: '질량_kg' } })

  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '측정' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe'))).toBe(true))
  const made = calls.find((c) => c.url.endsWith('/doe'))!.body as Record<string, unknown>
  expect(made.measures).toEqual([
    { name: '부피', kind: 'volume' },
    { name: '그룹_넓이', kind: 'region_area', region: '바닥' },
    { name: '질량_kg', kind: 'expr', expr: '부피 * 7.85e-6' },
  ])
})

test('Sobol · 중심 합성 — 방식마다 언제 쓰는지 알려 주고, Sobol 은 표본 수 · 시드를 받는다', async () => {
  const calls = mockApi(9)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8, 12' } })
  fireEvent.click(screen.getByLabelText('방법'))
  fireEvent.click(await screen.findByRole('option', { name: 'Sobol 수열' }))
  expect(screen.getByText(/같은 수열을 이어서 생성/)).toBeInTheDocument()
  expect(screen.getByLabelText(/표본 수/)).toBeInTheDocument()
  await waitFor(() => expect(calls.some((c) => (c.body as Record<string, unknown> | null)?.method === 'sobol')).toBe(true))

  fireEvent.click(screen.getByLabelText('방법'))
  fireEvent.click(await screen.findByRole('option', { name: '중심 합성 (CCF)' }))
  expect(screen.getByText(/2차 응답면/)).toBeInTheDocument()
  expect(screen.queryByLabelText(/표본 수/)).toBeNull()
})

test('「중간면 STEP 도」 를 켜면 점마다 중간면을 내라고 보낸다', async () => {
  const calls = mockApi(5)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '구간' }))
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: 'shell' } })
  fireEvent.click(screen.getByRole('checkbox', { name: /중간면 STEP 출력/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe'))).toBe(true))
  expect(calls.find((c) => c.url.endsWith('/doe'))!.body).toMatchObject({ outputs: ['midsurface'] })
})

test('식으로 정의된 변수는 인자가 아니다 — 따라가는 식으로 보이고 서버에 보내지 않는다', async () => {
  const calls = mockApi(2)
  const derived: Recipe = { ...RECIPE, params: { ...RECIPE.params, 간격: '=길이 / 2' } }
  render(<DoeForm recipe={derived} onCreated={() => {}} />)
  expect(screen.getByLabelText('식으로 정의된 변수')).toHaveTextContent('간격 =길이 / 2')
  expect(screen.queryByLabelText('간격 고정값')).not.toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '값 목록' }))
  fireEvent.change(screen.getByLabelText('두께 값 목록'), { target: { value: '4, 8' } })
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '식 변수' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '생성' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe'))).toBe(true))
  const made = calls.find((c) => c.url.endsWith('/doe'))!.body as { factors: { name: string }[] }
  expect(made.factors.map((one) => one.name).sort()).toEqual(['길이', '두께'])
})

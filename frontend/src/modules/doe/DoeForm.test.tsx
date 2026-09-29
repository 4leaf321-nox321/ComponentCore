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
  expect(screen.getByText(/바꿀 변수를 하나는 고르세요/)).toBeInTheDocument()

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
  await waitFor(() => expect(screen.getByText(/200 개까지 만듭니다/)).toBeInTheDocument())
  expect(screen.getByRole('button', { name: '만들기' })).toBeDisabled()
})

test('변수가 없으면 어디서 어떻게 만드는지 알려 주고, 편집기로 보내 준다', () => {
  const onEditRecipe = vi.fn()
  render(<DoeForm recipe={{ nodes: [] }} onCreated={() => {}} onEditRecipe={onEditRecipe} />)
  expect(screen.getByText(/먼저 도면에 「변수」 를 만들어야 합니다/)).toBeInTheDocument()
  expect(screen.getByText(/fx/)).toBeInTheDocument() // 어느 단추를 누르는지까지
  fireEvent.click(screen.getByRole('button', { name: '도면 고치러 가기' }))
  expect(onEditRecipe).toHaveBeenCalled()
})

test('「구간」 으로 바꾸고 칸을 손대지 않아도 시작 · 끝 · 단계가 채워져 서버로 간다', async () => {
  const calls = mockApi(5)
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  fireEvent.click(screen.getAllByRole('combobox')[0])
  fireEvent.click(await screen.findByRole('option', { name: '구간' }))
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: 'test1' } })
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/doe/preview'))).toBe(true))
  await waitFor(() => expect(screen.getByRole('button', { name: '만들기' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '만들기' }))
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
  await waitFor(() => expect(screen.getByRole('button', { name: '만들기' })).toBeEnabled())
  const before = calls.filter((c) => c.url.endsWith('/doe/preview')).length

  // 단계를 다 지운다 — 1 로 되돌리지 않고 빈 채로 둔다. 서버에 묻지 않고 만들기가 막힌다.
  fireEvent.change(screen.getByLabelText('두께 단계'), { target: { value: '' } })
  expect(screen.getByLabelText('두께 단계')).toHaveValue(null)
  expect(screen.getByRole('button', { name: '만들기' })).toBeDisabled()
  expect(screen.getByText('빈 칸을 채우면 설계점을 셉니다.')).toBeInTheDocument()
  await new Promise((r) => setTimeout(r, 50))
  expect(calls.filter((c) => c.url.endsWith('/doe/preview'))).toHaveLength(before)

  // 처음부터 친다 — 3.
  fireEvent.change(screen.getByLabelText('두께 단계'), { target: { value: '3' } })
  expect(screen.getByLabelText('두께 단계')).toHaveValue(3)
  await waitFor(() => expect(screen.getByRole('button', { name: '만들기' })).toBeEnabled())
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
  expect(screen.getByText('지금: AL5052')).toBeInTheDocument()
  expect(screen.getByText(/시뮬레이션 조건\(구속 · 하중 · 접촉 · 물성 · 해석 설정\)이 함께 실려/)).toBeInTheDocument()
  expect(screen.getByText(/저장하지 않은 것은 실리지 않습니다/)).toBeInTheDocument()

  // 재료만 훑어도 된다 — 치수는 모두 고정.
  fireEvent.click(screen.getByLabelText('블록 후보 AL5052'))
  fireEvent.click(screen.getByLabelText('블록 후보 SECC'))
  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '재료 훑기' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '만들기' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '만들기' }))
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
  const add = await screen.findByLabelText('바꿔 볼 칸 더하기')
  await waitFor(() => expect(add.querySelectorAll('option').length).toBeGreaterThan(1))
  fireEvent.change(add, { target: { value: 'contacts|블록-판|type' } })
  fireEvent.click(screen.getByLabelText('접촉 「블록-판」 · 종류 후보 본딩'))
  fireEvent.click(screen.getByLabelText('접촉 「블록-판」 · 종류 후보 마찰'))
  // 블록 탄성계수에 배율.
  fireEvent.change(await screen.findByLabelText('블록 배율 물성'), { target: { value: '탄성계수' } })
  fireEvent.change(screen.getByLabelText('블록 배율 값'), { target: { value: '0.9, 1.1' } })

  fireEvent.change(screen.getByLabelText('이름'), { target: { value: '조건 훑기' } })
  await waitFor(() => expect(screen.getByRole('button', { name: '만들기' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '만들기' }))
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

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { AssemblyEditor, sourceLink } from '@/modules/works/AssemblyEditor'

const WORKS = {
  items: [
    { id: 'w-part', name: '센서 브래킷', kind: 'part', current_version: 2 },
    { id: 'w-jig', name: '시험 지그', kind: 'jig', current_version: 1 },
  ],
  total: 2,
  limit: 100,
  offset: 0,
}

function Host({ initial = { version: 1, nodes: [] } }: { initial?: Recipe }) {
  const [recipe, setRecipe] = useState<Recipe>(initial)
  return (
    <>
      <AssemblyEditor value={recipe} onChange={setRecipe} />
      <pre data-testid="recipe">{JSON.stringify(recipe)}</pre>
    </>
  )
}
const recipeNow = () => JSON.parse(screen.getByTestId('recipe').textContent!) as Recipe

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/works') ? WORKS : { items: [], total: 0, limit: 100, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
})

let lastViewer: { dragPart?: string | null; onMoved?: (part: string, delta: { translate: [number, number, number]; rotate: [number, number, number] }) => void } = {}
vi.mock('@/shared/viewer/PickViewer', () => ({
  default: (props: { partColors?: Record<string, number>; dragPart?: string | null; onMoved?: (part: string, delta: { translate: [number, number, number]; rotate: [number, number, number] }) => void }) => {
    lastViewer = props
    return <div data-testid="viewer">{JSON.stringify(props.partColors ?? {})}</div>
  },
}))

test('3D 에서 끌어 놓으면 자리에 더해지고, 식으로 묶인 축은 건드리지 않고 말한다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/cad/recipe/check')
      ? { ok: true, problems: [] }
      : url.includes('/cad/recipe/mesh')
        ? { summary: { bbox: { size: [1, 1, 1] } }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] } }
        : url.includes('/cad/recipe/interference')
          ? { ok: true, tolerance: 0.5, total_volume: 0, checked_pairs: 1, parts: [], items: [] }
          : url.includes('/works')
            ? WORKS
            : { items: [], total: 0, limit: 100, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<Host />)
  fireEvent.click(await screen.findByRole('button', { name: /시험 지그/ }))
  await waitFor(() => expect(screen.getByTestId('viewer')).toBeInTheDocument())
  // 가져오면 고른 상태 — 손잡이가 그것에 붙는다.
  await waitFor(() => expect(lastViewer.dragPart).toBe('시험_지그'))
  act(() => lastViewer.onMoved!('시험_지그', { translate: [10, 0, 2.5], rotate: [0, 0, 0] }))
  expect((recipeNow().nodes[0] as { translate: number[] }).translate).toEqual([10, 0, 2.5])
  act(() => lastViewer.onMoved!('시험_지그', { translate: [0, -4, 0], rotate: [0, 0, 90] }))
  expect((recipeNow().nodes[0] as { translate: number[]; rotate: number[] }).translate).toEqual([10, -4, 2.5])
  expect((recipeNow().nodes[0] as { rotate: number[] }).rotate).toEqual([0, 0, 90])

})

test('식으로 묶인 축은 끌기가 건드리지 않고 말한다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/cad/recipe/check')
      ? { ok: true, problems: [] }
      : url.includes('/cad/recipe/mesh')
        ? { summary: { bbox: { size: [1, 1, 1] } }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] } }
        : url.includes('/cad/recipe/interference')
          ? { ok: true, tolerance: 0.5, total_volume: 0, checked_pairs: 0, parts: [], items: [] }
          : url.includes('/works')
            ? WORKS
            : { items: [], total: 0, limit: 100, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  function Bound() {
    const [recipe, setRecipe] = useState<Recipe>({
      version: 1,
      params: { 높이: 5 },
      nodes: [
        { id: '지그', op: 'component', source: 'work:w-jig', label: '시험 지그', translate: [0, 0, '=높이'], rotate: [0, 0, 0] },
        { id: '조립', op: 'group', targets: ['지그'] },
      ],
    })
    return (
      <>
        <AssemblyEditor value={recipe} onChange={setRecipe} />
        <pre data-testid="recipe">{JSON.stringify(recipe)}</pre>
      </>
    )
  }
  render(<Bound />)
  await waitFor(() => expect(screen.getByTestId('viewer')).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: '시험 지그' })) // 목록에서 고른다
  await waitFor(() => expect(lastViewer.dragPart).toBe('지그'))
  act(() => lastViewer.onMoved!('지그', { translate: [1, 1, 1], rotate: [0, 0, 0] }))
  expect((recipeNow().nodes[0] as { translate: (number | string)[] }).translate).toEqual([1, 1, '=높이'])
  expect(screen.getByText(/위치 Z은\(는\) 수식으로 연결되어 있어/)).toBeInTheDocument()
})

test('구성품끼리 겹치면 배지와 함께 어느 것끼리 얼마나인지 말하고, 3D 에서 빨갛다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/cad/recipe/check')
      ? { ok: true, problems: [] }
      : url.includes('/cad/recipe/mesh')
        ? { summary: { bbox: { size: [1, 1, 1] } }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] } }
        : url.includes('/cad/recipe/interference')
          ? { ok: false, tolerance: 0.5, total_volume: 1234.5, checked_pairs: 1, parts: ['센서_브래킷', '시험_지그'], items: [{ a: '센서_브래킷', b: '시험_지그', volume: 1234.5, ok: false }] }
          : url.includes('/works')
            ? WORKS
            : { items: [], total: 0, limit: 100, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<Host />)
  fireEvent.click(await screen.findByRole('button', { name: /센서 브래킷/ }))
  fireEvent.click(screen.getByRole('button', { name: /시험 지그/ }))
  expect(await screen.findByText(/센서_브래킷 × 시험_지그 1,234.5 mm³/, {}, { timeout: 3000 })).toBeInTheDocument()
  // 겹친 둘은 빨강(0xef4444).
  await waitFor(() => expect(JSON.parse(screen.getByTestId('viewer').textContent!)).toEqual({ 센서_브래킷: 0xef4444, 시험_지그: 0xef4444 }))
})

test('라이브러리에서 가져오면 component 피처가 생기고 묶음이 따라붙는다', async () => {
  render(<Host />)
  fireEvent.click(await screen.findByRole('button', { name: /센서 브래킷/ }))
  fireEvent.click(screen.getByRole('button', { name: /시험 지그/ }))
  // 가져온 것은 왼쪽 「구성」 목록에 선다 — 라이브러리 단추와는 별개의 줄이다.
  expect(screen.getByRole('button', { name: '센서 브래킷 편집' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '시험 지그 제거' })).toBeInTheDocument()

  const nodes = recipeNow().nodes
  expect(nodes.map((one) => one.op)).toEqual(['component', 'component', 'group'])
  expect(nodes[0]).toMatchObject({ source: 'work:w-part', translate: [0, 0, 0] })
  // 묶음은 손으로 만들지 않는다 — 가져온 것이 늘 모두 들어간다.
  expect(nodes[2]).toMatchObject({ op: 'group', targets: [nodes[0].id, nodes[1].id] })
})

test('놓인 것의 자리와 구성품 치수에 변수를 물릴 수 있다', async () => {
  render(<Host />)
  fireEvent.click(await screen.findByRole('button', { name: /시험 지그/ }))
  // 자리 · 회전 · 치수 덮어쓰기는 목록의 「편집」 이 여는 창에서.
  expect(screen.queryByLabelText('시험 지그 Z')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '시험 지그 편집' }))
  fireEvent.change(await screen.findByLabelText('시험 지그 Z'), { target: { value: '25' } })
  expect((recipeNow().nodes[0] as { translate: number[] }).translate).toEqual([0, 0, 25])

  // 가져온 도면의 변수를 덮어쓸 칸을 더한다 — 여기에 =조립변수 를 넣는다.
  fireEvent.change(screen.getByLabelText('시험 지그 덮어쓸 변수 이름'), { target: { value: '높이' } })
  fireEvent.submit(screen.getByLabelText('시험 지그 덮어쓸 변수 이름').closest('form')!)
  await waitFor(() => expect(screen.getByLabelText('시험 지그 높이')).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: '시험 지그 높이 변수 지정' }))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '지그_높이' } })
  fireEvent.change(screen.getByLabelText('새 변수 값'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))

  const now = recipeNow()
  expect(now.params).toEqual({ 지그_높이: 30 })
  expect((now.nodes[0] as { params: Record<string, string> }).params).toEqual({ 높이: '=지그_높이' })
})

test('구성품마다 **원본 도면으로 가는 길**이 있다 — 여기선 자리만 고친다', async () => {
  const placed: Recipe = {
    version: 1,
    nodes: [{ id: 'c1', op: 'component', source: 'work:w-part', label: '센서 브래킷' }],
  } as unknown as Recipe
  render(<AssemblyEditor value={placed} onChange={vi.fn()} />)

  const link = await screen.findByRole('link', { name: /원본 열기/ })
  expect(link.getAttribute('href')).toBe('/works/w-part')
  // 새 탭 — 고치던 배치를 잃지 않게.
  expect(link.getAttribute('target')).toBe('_blank')
  // 어디서 무엇을 고치는지 한 줄로 말해 준다(모양을 고치러 온 사람이 막히던 자리).
  expect(screen.getByText(/위치, 회전, 치수 덮어쓰기/)).toBeTruthy()
})

test('공용 부품 · 지그도 제 화면으로 간다', () => {
  expect(sourceLink('part:p1')).toBe('/parts/p1')
  expect(sourceLink('jig:j1')).toBe('/jigs/j1')
  // 모르는 꼴이면 단추를 안 그린다 — 엉뚱한 데로 보내는 것보다 없는 편이 낫다.
  expect(sourceLink('알수없음')).toBeNull()
})

/** AI 가 바퀴 · 상체를 **조립 안에 바로 그린** 작업(로봇 병사) — 가져온 것은 차체 하나뿐이다. */
const DRAWN_IN_PLACE = {
  version: 1,
  params: { 상체_각도: 0 },
  nodes: [
    { id: '차체', op: 'component', source: 'work:w-part', label: '센서 브래킷', translate: [0, 0, 0], rotate: [0, 0, 0] },
    { id: '바퀴', op: 'cylinder', radius: 5, height: 3 },
    { id: '상체_몸', op: 'box', length: 10, width: 10, height: 10 },
    { id: '상체', op: 'transform', target: '상체_몸', rotate: [0, '=상체_각도', 0] },
    { id: '전체', op: 'group', targets: ['차체', '바퀴', '상체'] },
  ],
  result: '전체',
} as unknown as Recipe

function mockCad() {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/cad/recipe/check')
      ? { ok: true, problems: [] }
      : url.includes('/cad/recipe/mesh')
        ? { summary: { bbox: { size: [1, 1, 1] } }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] } }
        : url.includes('/cad/recipe/interference')
          ? { ok: true, tolerance: 0.5, total_volume: 0, checked_pairs: 3, parts: [], items: [] }
          : url.includes('/works')
            ? WORKS
            : { items: [], total: 0, limit: 100, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}
const ids = () => recipeNow().nodes.map((one) => one.id)
const groupOf = () => recipeNow().nodes.find((one) => one.op === 'group') as { id: string; targets: string[] }

test('조립 안에서 직접 그린 형상도 「구성」 에 서고 — 시뮬레이션 조건의 파트 수와 같다 — 3D 와 같은 색이다', async () => {
  mockCad()
  render(<Host initial={DRAWN_IN_PLACE} />)
  expect(screen.getByText('구성 (3)')).toBeInTheDocument()
  const drawn = within(screen.getByRole('list', { name: '직접 그린 형상' }))
  expect(drawn.getAllByRole('listitem').map((one) => one.textContent)).toEqual(['바퀴직접 그림', '상체직접 그림'])
  // 고치는 단추는 없다 — 고치는 길(부품으로 그려 가져오기)을 말해 준다.
  expect(screen.queryByRole('button', { name: '바퀴 편집' })).toBeNull()
  expect(screen.getByText(/부품 작업으로 따로 그린 후/)).toBeInTheDocument()
  await waitFor(() => expect(Object.keys(JSON.parse(screen.getByTestId('viewer').textContent!))).toEqual(['차체', '바퀴', '상체']))
})

test('구성품을 옮겨도 직접 그린 형상 · 결과 묶음 · result 는 그대로다', async () => {
  render(<Host initial={DRAWN_IN_PLACE} />)
  fireEvent.click(screen.getByRole('button', { name: '센서 브래킷 편집' }))
  fireEvent.change(await screen.findByLabelText('센서 브래킷 Z'), { target: { value: '12' } })
  expect(ids()).toEqual(['차체', '바퀴', '상체_몸', '상체', '전체'])
  expect((recipeNow().nodes[0] as { translate: number[] }).translate).toEqual([0, 0, 12])
  expect(groupOf().targets).toEqual(['차체', '바퀴', '상체'])
  expect(recipeNow().result).toBe('전체')
  expect(recipeNow().nodes[3]).toEqual(DRAWN_IN_PLACE.nodes[3])

  // 이름 — 그린 노드의 id 와 겹치면 받지 않는다(id 가 둘이면 레시피가 깨진다). 바꾸면 묶음도 따라간다.
  fireEvent.change(screen.getByLabelText('센서 브래킷 이름'), { target: { value: '바퀴' } })
  expect(ids()[0]).toBe('차체')
  fireEvent.change(screen.getByLabelText('센서 브래킷 이름'), { target: { value: '몸체' } })
  expect(ids()).toEqual(['몸체', '바퀴', '상체_몸', '상체', '전체'])
  expect(groupOf().targets).toEqual(['몸체', '바퀴', '상체'])
})

test('새로 가져온 것은 마지막 구성품 뒤 · 묶음 앞에 서고 묶음에 들며, 빼면 그린 것만 남는다', async () => {
  render(<Host initial={DRAWN_IN_PLACE} />)
  fireEvent.click(await screen.findByRole('button', { name: /시험 지그/ }))
  expect(ids()).toEqual(['차체', '시험_지그', '바퀴', '상체_몸', '상체', '전체'])
  expect(groupOf().targets).toEqual(['차체', '바퀴', '상체', '시험_지그'])

  fireEvent.click(screen.getByRole('button', { name: '센서 브래킷 제거' }))
  fireEvent.click(screen.getByRole('button', { name: '시험 지그 제거' }))
  expect(ids()).toEqual(['바퀴', '상체_몸', '상체', '전체'])
  expect(groupOf().targets).toEqual(['바퀴', '상체'])
  expect(recipeNow().result).toBe('전체')
  expect(screen.getByText('구성 (2)')).toBeInTheDocument()
})

test('묶음 없이 그린 결과가 있으면, 가져올 때 만드는 묶음에 그것도 든다', async () => {
  render(<Host initial={{ version: 1, nodes: [{ id: '받침', op: 'box', length: 10, width: 10, height: 2 }] } as unknown as Recipe} />)
  expect(within(screen.getByRole('list', { name: '직접 그린 형상' })).getByText('받침')).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: /시험 지그/ }))
  expect(recipeNow().nodes.map((one) => one.op)).toEqual(['box', 'component', 'group'])
  expect(groupOf()).toMatchObject({ id: '조립', targets: ['시험_지그', '받침'] })
})

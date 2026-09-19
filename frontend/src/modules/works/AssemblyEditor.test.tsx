import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { AssemblyEditor } from '@/modules/works/AssemblyEditor'

const WORKS = {
  items: [
    { id: 'w-part', name: '센서 브래킷', kind: 'part', current_version: 2 },
    { id: 'w-jig', name: '시험 지그', kind: 'jig', current_version: 1 },
  ],
  total: 2,
  limit: 100,
  offset: 0,
}

function Host() {
  const [recipe, setRecipe] = useState<Recipe>({ version: 1, nodes: [] })
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

vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({ partColors }: { partColors?: Record<string, number> }) => <div data-testid="viewer">{JSON.stringify(partColors ?? {})}</div>,
}))

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
  expect(screen.getByRole('button', { name: '시험 지그 빼기' })).toBeInTheDocument()

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
  fireEvent.click(screen.getByRole('button', { name: '시험 지그 높이 변수로' }))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '지그_높이' } })
  fireEvent.change(screen.getByLabelText('새 변수 값'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: '만들기' }))

  const now = recipeNow()
  expect(now.params).toEqual({ 지그_높이: 30 })
  expect((now.nodes[0] as { params: Record<string, string> }).params).toEqual({ 높이: '=지그_높이' })
})

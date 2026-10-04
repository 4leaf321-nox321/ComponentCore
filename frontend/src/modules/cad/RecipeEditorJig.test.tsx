/**
 * 생성된 지그를 고칠 때 — 제품을 옆에 놓고(저장하지 않는다) 요소마다 간섭을 본다. 고른 요소는
 * 3D 에서 끌어 옮긴다.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'
import type { JigProduct } from '@/modules/works/jigEdit'

const JIG = {
  version: 1,
  params: { 받침_높이: 12 },
  nodes: [
    { id: '바닥판', op: 'box', length: 100, width: 80, height: 10, at: [0, 0, 0] },
    { id: '받침_1', op: 'cylinder', radius: 5, height: '=받침_높이', at: [-30, -20, 0] },
    { id: '지그', op: 'group', targets: ['바닥판', '받침_1'] },
  ],
  result: '지그',
} as unknown as Recipe

const PRODUCT: JigProduct = {
  available: true,
  label: '브래킷',
  lift_param: '받침_높이',
  node: { id: '제품', op: 'component', source: 'work:w1@1', translate: [0, 0, '=받침_높이 + 0'] },
}

type Viewer = { partColors?: Record<string, number>; dragPart?: string | null; onMoved?: (part: string, delta: { translate: [number, number, number]; rotate: [number, number, number] }) => void }
let lastViewer: Viewer = {}
vi.mock('@/shared/viewer/PickViewer', () => ({
  default: (props: Viewer) => {
    lastViewer = props
    return <div data-testid="viewer">{JSON.stringify(props.partColors ?? {})}</div>
  },
}))

function serve(hit: boolean) {
  const asked: { url: string; body: Recipe | null }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? (JSON.parse(String(init.body)).recipe as Recipe) : null
    asked.push({ url, body })
    const out = url.endsWith('/cad/recipe/check')
      ? { ok: true, problems: [] }
      : url.endsWith('/cad/recipe/mesh')
        ? { summary: { bbox: { size: [1, 1, 1] }, volume: 1, face_count: 1, nodes: [], warnings: [], is_sketch: false }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] } }
        : url.endsWith('/cad/recipe/interference')
          ? {
              ok: !hit,
              tolerance: 0.5,
              total_volume: hit ? 12.5 : 0,
              items: [{ a: '받침_1', b: '제품', volume: hit ? 12.5 : 0, ok: !hit }],
              parts: ['바닥판', '받침_1', '제품'],
              checked_pairs: 3,
            }
          : {}
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return asked
}

function Host({ product }: { product: JigProduct | null }) {
  const [recipe, setRecipe] = useState<Recipe>(JIG)
  return (
    <>
      <RecipeEditor value={recipe} onChange={setRecipe} jigProduct={product} />
      <pre data-testid="recipe">{JSON.stringify(recipe)}</pre>
    </>
  )
}

test('제품을 덧붙여 간섭을 묻고, 걸린 요소를 빨갛게 · 까닭을 말한다 — 저장하는 레시피에는 제품이 없다', async () => {
  const asked = serve(true)
  render(<Host product={PRODUCT} />)
  expect(await screen.findByText(/간섭: 받침_1 × 제품 12\.5 mm³/)).toBeInTheDocument()
  const checked = asked.find((one) => one.url.endsWith('/cad/recipe/interference'))!.body!
  expect((checked.nodes as { id: string }[]).map((one) => one.id)).toEqual(['바닥판', '받침_1', '제품', '지그'])
  await waitFor(() => expect(lastViewer.partColors).toMatchObject({ 제품: 0x60a5fa, 받침_1: 0xef4444 }))
  expect(JSON.parse(screen.getByTestId('recipe').textContent!).nodes).toHaveLength(3)

  // 받침을 고르면 화살표가 붙고, 끌어 놓으면 XY 만 옮긴다.
  fireEvent.click(screen.getByText('받침_1').closest('button')!)
  await waitFor(() => expect(lastViewer.dragPart).toBe('받침_1'))
  lastViewer.onMoved!('받침_1', { translate: [4, 1, 9], rotate: [0, 0, 0] })
  await waitFor(() => {
    const now = JSON.parse(screen.getByTestId('recipe').textContent!) as { nodes: { id: string; at?: unknown }[] }
    expect(now.nodes.find((one) => one.id === '받침_1')!.at).toEqual([-26, -19, 0])
  })
})

test('제품을 숨기면 그냥 도면이고, 자리를 모르면 까닭을 말한다', async () => {
  const asked = serve(false)
  const { unmount } = render(<Host product={PRODUCT} />)
  expect(await screen.findByText(/제품\(‘브래킷’\)과 요소 2개를 검사했습니다/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '제품 숨기기' }))
  expect(screen.queryByText(/요소 2개를 검사했습니다/)).toBeNull()
  // 0.5초 쉬었다가 제품 없는 도면으로 다시 그린다.
  await waitFor(() => {
    const last = asked.filter((one) => one.url.endsWith('/cad/recipe/mesh')).at(-1)!.body!
    expect((last.nodes as { id: string }[]).some((one) => one.id === '제품')).toBe(false)
  })
  unmount()

  render(<Host product={{ available: false, reason: '제품의 자리를 모릅니다.' }} />)
  expect(await screen.findByText('제품의 자리를 모릅니다.')).toBeInTheDocument()
})

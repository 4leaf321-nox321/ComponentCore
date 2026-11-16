import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Recipe } from '@/modules/cad/api'
import { DoeForm } from '@/modules/doe/DoeForm'

vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({ measureMarks }: { measureMarks?: { segments: { text?: string; tone?: string }[] } }) => (
    <div data-testid="viewer" data-segments={(measureMarks?.segments ?? []).map((one) => `${one.text}:${one.tone}`).join('|')} />
  ),
}))

const RECIPE: Recipe = {
  params: { 두께: 6, 길이: 90 },
  nodes: [{ id: 'b', op: 'box', length: '=길이', width: 40, height: '=두께' }],
}

const one = (name: string, value: number) => ({ name, value, status: 'dimension', kind: 'distance', from: [0, 0, 0], to: [value, 0, 0], at: null, faces: [0], places: 1, message: null })

test('새 DOE 는 범위를 주는 칸 위에 도면과 변수 치수를 보이고, 변수 행에 마우스를 올리면 그 치수만 긋는다', async () => {
  window.localStorage.clear()
  const asked: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    asked.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null })
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    if (url.endsWith('/cad/recipe/mesh')) {
      return json({ summary: {}, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [{ index: 0, kind: 'plane', center: [0, 0, 0], normal: [0, 0, 1], area: 1, vertices: [], triangles: [] }], edges: [] } })
    }
    if (url.endsWith('/cad/recipe/param-dims')) return json({ face_count: 1, dims: [one('두께', 6), one('길이', 90)] })
    return json({ count: 1, max: 200, max_samples: 500, too_many: false, points: [], varying: [] })
  })
  render(<DoeForm recipe={RECIPE} onCreated={() => {}} />)
  await waitFor(() => expect(screen.getByTestId('viewer').getAttribute('data-segments')).toBe('두께 = 6:live|길이 = 90:live'))
  // 찾는 것은 인자가 될 변수 — 도면의 숫자 변수.
  expect(asked.find((one) => one.url.endsWith('/param-dims'))?.body).toEqual({ recipe: RECIPE, names: ['두께', '길이'] })

  fireEvent.mouseEnter(screen.getByTitle('길이').parentElement!)
  expect(screen.getByTestId('viewer').getAttribute('data-segments')).toBe('길이 = 90:live')
  fireEvent.mouseLeave(screen.getByTitle('길이').parentElement!)
  expect(screen.getByTestId('viewer').getAttribute('data-segments')).toBe('두께 = 6:live|길이 = 90:live')

  // 접으면 묻지도 그리지도 않는다 — 다음에 열 때도 접힌 채다.
  fireEvent.click(screen.getByRole('button', { name: '숨기기' }))
  expect(screen.queryByTestId('viewer')).toBeNull()
  expect(screen.getByRole('button', { name: '표시' })).toBeInTheDocument()
})

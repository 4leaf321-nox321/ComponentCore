import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Recipe } from '@/modules/cad/api'
import { DrawingDialog } from '@/modules/cad/DrawingDialog'

const BOX: Recipe = { nodes: [{ id: 'b', op: 'box', length: 40, width: 30, height: 10 }] }
const SUMMARY = { sheet: 'A3', scale: '2:1', holes: [{ label: 'A1', spec: 'Ø6 관통', view: '평면도', x: 20, y: 15 }], dimensions: [], notes: [] }

const bodies: Record<string, unknown>[] = []

beforeEach(() => {
  bodies.length = 0
  URL.createObjectURL = vi.fn(() => 'blob:drawing')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    bodies.push({ url, ...(JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>) })
    if (url.includes('format=json')) return new Response(JSON.stringify(SUMMARY), { status: 200, headers: { 'Content-Type': 'application/json' } })
    return new Response('<svg/>', { status: 200, headers: { 'Content-Type': 'image/svg+xml' } })
  })
})

test('작업 이름을 표제란에 먼저 적고, 미리 본 뒤 PDF 로 받는다', async () => {
  render(<DrawingDialog open recipe={BOX} defaultTitle="브래킷" onClose={() => {}} />)
  expect(screen.getByLabelText('도면 이름')).toHaveValue('브래킷')
  await waitFor(() => expect(screen.getByAltText('도면 미리보기')).toBeInTheDocument())
  expect(screen.getByText(/축척 2:1 · 구멍 1 개/)).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('재료'), { target: { value: 'SS400' } })
  fireEvent.change(screen.getByLabelText('용지'), { target: { value: 'A4' } })
  await waitFor(() => expect(bodies.some((one) => one.material === 'SS400' && one.sheet === 'A4')).toBe(true))

  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  fireEvent.click(screen.getByRole('button', { name: 'PDF 받기' }))
  await waitFor(() => expect(click).toHaveBeenCalled())
  const pdf = bodies.find((one) => String(one.url).includes('format=pdf'))
  expect(pdf).toMatchObject({ title: '브래킷', material: 'SS400', sheet: 'A4', recipe: BOX })
})

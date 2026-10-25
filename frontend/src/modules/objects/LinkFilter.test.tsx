import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { LinkFilter } from '@/modules/objects/LinkFilter'

const KINDS = [
  { relation: 'uses_part', label: '적용 모델', incoming: true, other_types: [{ slug: 'base_model', label: '기본 모델' }] },
  { relation: 'design_part', label: '서비스 부품', incoming: true, other_types: [{ slug: 'part', label: '서비스 부품' }] },
]

function serve(kinds: unknown) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/ontology/kinds') ? kinds : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}

test('기준정보 칸을 고르면 그 상대 타입의 고르개가 선다', async () => {
  serve(KINDS)
  render(<LinkFilter base="parts" value={null} onChange={() => {}} />)
  const select = await screen.findByRole('combobox', { name: '기준정보 칸' })
  expect(screen.getAllByRole('option').map((one) => one.textContent)).toEqual(['칸 고르기', '적용 모델', '서비스 부품'])
  fireEvent.change(select, { target: { value: 'uses_part:in' } })
  expect(await screen.findByRole('combobox', { name: '적용 모델 고르기' })).toBeInTheDocument()
})

test('고른 것은 칩으로 남고 × 로 푼다', async () => {
  serve(KINDS)
  const changed = vi.fn()
  render(
    <LinkFilter base="parts" value={{ relation: 'uses_part', label: '적용 모델', objectId: 'm5', objectLabel: 'P5 플립' }} onChange={changed} />,
  )
  expect(await screen.findByText('적용 모델: P5 플립')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '기준정보 거르개 풀기' }))
  expect(changed).toHaveBeenCalledWith(null)
})

test('칸이 없으면 아무것도 안 그린다', async () => {
  serve([])
  const { container } = render(<LinkFilter base="jigs" value={null} onChange={() => {}} />)
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
  expect(container).toBeEmptyDOMElement()
})

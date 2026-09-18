import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import type { Work } from '@/modules/works/api'
import { WorkDoeTab } from '@/modules/doe/WorkDoeTab'

function work(params: Record<string, number>, version = 3): Work {
  return {
    id: 'w1',
    name: '브래킷',
    current_version: version,
    current: { recipe: { params, nodes: [] } },
  } as unknown as Work
}

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
})

test('무엇을 기준으로 훑는지 — 저장된 버전과 변수를 적는다', async () => {
  render(
    <MemoryRouter>
      <WorkDoeTab workId="w1" work={work({ 두께: 6, 길이: 90 })} />
    </MemoryRouter>,
  )
  expect(await screen.findByText(/저장된/)).toHaveTextContent('v3')
  expect(screen.getByText(/변수 2개 \(두께, 길이\)/)).toBeInTheDocument()
})

test('저장하지 않은 고침이 있으면 그것 때문이라고 말한다', async () => {
  render(
    <MemoryRouter>
      <WorkDoeTab workId="w1" work={work({})} pendingDraft onEditRecipe={() => {}} />
    </MemoryRouter>,
  )
  expect(await screen.findByText(/저장하지 않은 고침/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '부품 탭으로' })).toBeInTheDocument()
  expect(screen.getByText(/변수 없음/)).toBeInTheDocument()
})

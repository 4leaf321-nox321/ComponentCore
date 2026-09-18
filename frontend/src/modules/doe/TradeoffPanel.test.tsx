import { render, screen, waitFor } from '@testing-library/react'

import type { DoeStudy, TradeoffPoint } from '@/modules/doe/api'
import { TradeoffPanel } from '@/modules/doe/TradeoffPanel'

const POINTS: TradeoffPoint[] = [
  { number: 1, params: { 두께: 4 }, mass_g: 100, size_z: 12, comparable: true, pareto: true, score: 0.2 },
  { number: 2, params: { 두께: 8 }, mass_g: 150, size_z: 16, comparable: true, pareto: true, score: 0.5 },
  { number: 3, params: { 두께: 12 }, mass_g: 260, size_z: 12, comparable: true, pareto: false, score: 0.9 },
  { number: 4, params: { 두께: 0 }, comparable: false, pareto: false, score: null },
]

const STUDY = { id: 's1', done: 3 } as DoeStudy

test('지지 않는 점만 가려 보여 준다 — 한 값으로 합치지 않는다', async () => {
  const sent: unknown[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    sent.push(init?.body ? JSON.parse(String(init.body)) : null)
    return new Response(JSON.stringify({ objectives: [], points: POINTS, pareto_count: 2 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  const { container } = render(<TradeoffPanel study={STUDY} />)

  // 기본 목표 둘(질량 작게 · 높이 크게)을 서버에 그대로 묻는다.
  await waitFor(() => expect(sent.length).toBeGreaterThan(0))
  expect(sent[0]).toEqual([
    { key: 'mass_g', goal: 'min' },
    { key: 'size_z', goal: 'max' },
  ])

  // 지는 점(p3)과 못 견주는 점(p4)은 목록에 없다.
  await waitFor(() => expect(screen.getByText(/p1, p2/)).toBeInTheDocument())
  expect(screen.getAllByText(/지지 않는 점/).length).toBeGreaterThan(0)
  expect(screen.queryByText('p0003')).toBeNull()

  // 흩뿌림에는 견줄 수 있는 점 셋만 찍힌다(p4 는 값이 없다).
  expect(container.querySelectorAll('svg circle')).toHaveLength(3)
})

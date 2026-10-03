import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { placeOf } from '@/modules/search/api'
import { SimilarCard } from '@/modules/search/SimilarCard'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

test('어디서 왔나는 source 의 접두가 말한다', () => {
  expect(placeOf('work:1')).toEqual({ to: '/works/1', label: '내 작업' })
  expect(placeOf('part:2')).toEqual({ to: '/parts/2', label: '부품' })
  expect(placeOf('jig:3')).toEqual({ to: '/jigs/3', label: '지그' })
})

test('점수 · 왜 · 형상을 보이고, 비슷한 부품에는 그 부품의 지그를 붙인다', async () => {
  const bodies: unknown[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    bodies.push(JSON.parse(String(init?.body)))
    return json({
      reference: { source: 'part:p1' },
      compared: 7,
      items: [
        {
          source: 'part:p2',
          kind: 'part',
          name: '센서 브래킷 B',
          folder: '',
          version: 2,
          score: 0.93,
          parts: { size: 0.95, holes: 1 },
          why: ['크기 비슷', '구멍 같음'],
          shape: { size: [100, 60, 10], dims: [10, 60, 100], volume: 1, holes: [{ d: 6.6, n: 4, through: 4 }], hole_count: 4 },
          jigs: [{ source: 'jig:j9', name: '센서 브래킷 B 지그' }],
        },
        { source: 'jig:j3', kind: 'jig', name: '받침 지그', folder: '', version: 1, score: 0.41, parts: {}, why: ['크기 많이 다름'], shape: {}, part_name: '판' },
      ],
    })
  })
  render(
    <MemoryRouter>
      <SimilarCard source="part:p1" />
    </MemoryRouter>,
  )
  expect(await screen.findByText('센서 브래킷 B')).toHaveAttribute('href', '/parts/p2')
  expect(bodies[0]).toMatchObject({ source: 'part:p1', limit: 8 })
  expect(screen.getByText('93%')).toBeInTheDocument()
  expect(screen.getByText('구멍 같음')).toBeInTheDocument()
  expect(screen.getByText('100 × 60 × 10 · 구멍 Ø6.6×4')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '센서 브래킷 B 지그' })).toHaveAttribute('href', '/jigs/j9')
  expect(screen.getByText('부품: 판')).toBeInTheDocument()
})

test('색인이 없는 버전이면 서버의 말을 그대로 — 오류가 아니라 아직 못 견주는 것', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
    json({ error: { code: 'CCR-SEARCH-0003', message: '이 버전에는 형상 색인이 없습니다 — 관리자가 서버 화면에서 「형상 색인 채우기」.' } }, 400),
  )
  render(
    <MemoryRouter>
      <SimilarCard source="work:w1" />
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByText(/형상 색인 채우기/)).toBeInTheDocument())
})

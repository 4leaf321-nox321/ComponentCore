import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Conditions, ContactReport } from '@/modules/conditions/api'
import { ContactCheck } from '@/modules/conditions/ContactCheck'

const draft: Conditions = {
  named_selections: [{ name: '판 윗면', entity: 'face', select: { what: 'faces', body: '판' } }],
  materials: [],
  constraints: [],
  loads: [],
  contacts: [{ name: '판-받침', type: 'bonded', source: '받침 아랫면', target: '판 윗면' }],
  initial: [],
  analysis: { type: 'modal' },
  mesh_hints: [],
}

const REPORT: ContactReport = {
  touching: [
    { a: '판', b: '받침', area: 400, at: [0, 0, 3] },
    { a: '받침', b: '덮개', area: 400, at: [0, 0, 13] },
  ],
  missing: [{ a: '받침', b: '덮개', area: 400, at: [0, 0, 13] }],
  proposal: {
    named_selections: [
      { name: '받침-덮개 접촉면(받침)', entity: 'face', select: { what: 'faces', body: '받침' } },
      { name: '받침-덮개 접촉면(덮개)', entity: 'face', select: { what: 'faces', body: '덮개' } },
    ],
    contacts: [{ name: '본딩 받침-덮개', type: 'bonded', source: '받침-덮개 접촉면(받침)', target: '받침-덮개 접촉면(덮개)' }],
  },
  notes: [{ where: '바디 ‘받침’ · ‘덮개’', level: 'warn', text: '접촉 미정의: 인접 바디 …' }],
}

function serve(body: unknown) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )
}

test('접촉 미정의 인접 바디를 알리고, 누르면 본딩을 한 번에 생성한다', async () => {
  serve(REPORT)
  const onApply = vi.fn()
  render(<ContactCheck recipe={{ nodes: [] }} draft={draft} onApply={onApply} />)
  expect(await screen.findByText(/인접 바디 2쌍 · 접촉 미정의 1쌍/, {}, { timeout: 3000 })).toBeInTheDocument()
  expect(screen.getByText(/접촉 미정의: 인접 바디/)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /미정의 접촉을 본딩으로 생성 \(1쌍\)/ }))
  const next = onApply.mock.calls[0][0] as Conditions
  expect(next.named_selections.map((one) => one.name)).toEqual(['판 윗면', '받침-덮개 접촉면(받침)', '받침-덮개 접촉면(덮개)'])
  expect(next.contacts.map((one) => one.name)).toEqual(['판-받침', '본딩 받침-덮개'])
})

test('인접 바디가 없으면(단품) 아무것도 그리지 않는다', async () => {
  serve({ ...REPORT, touching: [], missing: [], proposal: { named_selections: [], contacts: [] }, notes: [] })
  const { container } = render(<ContactCheck recipe={{ nodes: [] }} draft={draft} onApply={vi.fn()} />)
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled(), { timeout: 3000 })
  expect(container.innerHTML).toBe('')
})

test('인접 바디가 없어도 잘못 걸린 접촉의 경고는 보인다', async () => {
  serve({
    ...REPORT,
    touching: [],
    missing: [],
    proposal: { named_selections: [], contacts: [] },
    notes: [{ where: '접촉 ‘판-받침’', level: 'warn', text: '접촉면 ‘받침 아랫면’과 대상면 ‘판 윗면’이 같은 면을 가리킵니다' }],
  })
  render(<ContactCheck recipe={{ nodes: [] }} draft={draft} onApply={vi.fn()} />)
  expect(await screen.findByText(/같은 면을 가리킵니다/, {}, { timeout: 3000 })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /미정의 접촉을 본딩으로 생성/ })).not.toBeInTheDocument()
})

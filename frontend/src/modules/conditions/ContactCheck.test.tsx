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
      { name: '받침-덮개 받침쪽', entity: 'face', select: { what: 'faces', body: '받침' } },
      { name: '받침-덮개 덮개쪽', entity: 'face', select: { what: 'faces', body: '덮개' } },
    ],
    contacts: [{ name: '받침-덮개', type: 'bonded', source: '받침-덮개 받침쪽', target: '받침-덮개 덮개쪽' }],
  },
  notes: [{ where: '바디 ‘받침’ · ‘덮개’', level: 'warn', text: '접촉 없이 맞닿은 바디 …' }],
}

function serve(body: unknown) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )
}

test('맞닿았는데 접촉이 없는 쌍을 말하고, 누르면 본딩을 한 번에 채운다', async () => {
  serve(REPORT)
  const onApply = vi.fn()
  render(<ContactCheck recipe={{ nodes: [] }} draft={draft} onApply={onApply} />)
  expect(await screen.findByText(/맞닿은 바디 쌍 2 · 접촉 없음 1/, {}, { timeout: 3000 })).toBeInTheDocument()
  expect(screen.getByText(/접촉 없이 맞닿은 바디/)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /맞닿은 면으로 본딩 채우기 \(1쌍\)/ }))
  const next = onApply.mock.calls[0][0] as Conditions
  expect(next.named_selections.map((one) => one.name)).toEqual(['판 윗면', '받침-덮개 받침쪽', '받침-덮개 덮개쪽'])
  expect(next.contacts.map((one) => one.name)).toEqual(['판-받침', '받침-덮개'])
})

test('맞닿은 쌍이 없으면(단품) 아무것도 그리지 않는다', async () => {
  serve({ ...REPORT, touching: [], missing: [], proposal: { named_selections: [], contacts: [] }, notes: [] })
  const { container } = render(<ContactCheck recipe={{ nodes: [] }} draft={draft} onApply={vi.fn()} />)
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled(), { timeout: 3000 })
  expect(container.innerHTML).toBe('')
})

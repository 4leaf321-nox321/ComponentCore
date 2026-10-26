import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { SimilarTagsPanel } from '@/modules/tagging/SimilarTagsPanel'

const GROUP = {
  type_slug: 'cc_tag',
  type_label: '일반 태그',
  keep: 'a',
  members: [
    { object_id: 'a', label: '굽힘시험', key: null, uses: 5, created_at: '2026-10-01T00:00:00Z' },
    { object_id: 'b', label: '굽힘 시험', key: null, uses: 2, created_at: '2026-10-02T00:00:00Z' },
    { object_id: 'c', label: '굽힘-시험', key: null, uses: 1, created_at: '2026-10-03T00:00:00Z' },
  ],
}

const INTO = { object_id: 'b', label: '굽힘 시험', type_slug: 'cc_tag', type_label: '일반 태그' }

function serve() {
  const asked: { url: string; method: string; body: string }[] = []
  let merged = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    asked.push({ url, method: init?.method ?? 'GET', body: String(init?.body ?? '') })
    let body: unknown = { groups: merged ? [] : [GROUP], notes: [] }
    if (url.endsWith('/tags/merge')) {
      merged = true
      body = { into: INTO, merged: 1, moved: 4, dropped: 1 }
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter>
      <SimilarTagsPanel />
    </MemoryRouter>,
  )
  return asked
}

test('추천한 것을 남기고 나머지를 합칠 것으로 고른다', async () => {
  serve()
  expect(await screen.findByRole('link', { name: '굽힘시험' })).toHaveAttribute('href', '/o/cc_tag/a')
  expect(screen.getByRole('radio', { name: '굽힘시험 남기기' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: '굽힘시험 합치기' })).toBeDisabled()
  expect(screen.getByRole('checkbox', { name: '굽힘 시험 합치기' })).toBeChecked()
  expect(screen.getByRole('button', { name: '2개를 「굽힘시험」에 합치기' })).toBeEnabled()
})

test('남길 것을 바꾸고 하나를 빼서 합치면 그것만 보내고 결과를 말한다', async () => {
  const asked = serve()
  fireEvent.click(await screen.findByRole('radio', { name: '굽힘 시험 남기기' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '굽힘-시험 합치기' }))
  fireEvent.click(screen.getByRole('button', { name: '1개를 「굽힘 시험」에 합치기' }))
  const dialog = await screen.findByRole('dialog')
  // 무엇이 지워지고 몇 건이 옮겨 가는지 적는다.
  expect(within(dialog).getByText(/「굽힘시험」이 지워지고, 붙어 있던 5건이/)).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: '합치기' }))
  await waitFor(() => expect(asked.some((one) => one.url.endsWith('/tags/merge'))).toBe(true))
  const sent = asked.find((one) => one.url.endsWith('/tags/merge'))
  expect(JSON.parse(sent?.body ?? '{}')).toEqual({ into: 'b', merge: ['a'] })
  expect(await screen.findByText(/「굽힘시험」을 「굽힘 시험」에 합쳤습니다 — 옮긴 것 4건, 이미 붙어/)).toBeInTheDocument()
  expect(await screen.findByText('비슷한 태그가 없습니다.')).toBeInTheDocument()
})

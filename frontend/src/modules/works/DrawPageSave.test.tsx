import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import DrawPage from '@/modules/works/DrawPage'

const WORK = {
  id: 'w1',
  name: '센서 브래킷',
  kind: 'part',
  current_version: 2,
  current: { number: 2, recipe: { nodes: [{ id: 'b', op: 'box', length: 40, width: 30, height: 10 }] } },
}

function mockApi() {
  const calls: { url: string; method: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.includes('/cad/recipe/check')
      ? { ok: true, problems: [] }
      : url.endsWith('/works/w1')
        ? WORK
        : url.includes('/works?') || url.endsWith('/works')
          ? init?.method === 'POST'
            ? { id: 'w-new' }
            : { items: [WORK], total: 1, limit: 50, offset: 0 }
          : url.includes('/works/w1/versions')
            ? { number: 3 }
            : { items: [], total: 0, limit: 50, offset: 0, templates: {}, template_labels: {}, schema: {} }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

async function loadExisting() {
  fireEvent.mouseDown(screen.getByRole('tab', { name: '파일' }))
  fireEvent.click(screen.getByRole('button', { name: /기존 작업/ }))
  fireEvent.click(await screen.findByRole('button', { name: '도면 가져오기' }))
  await waitFor(() => expect(screen.getAllByText('b').length).toBeGreaterThan(0))
}

test('기존 작업을 불러와 고쳤으면 「덮어 저장」 과 「새 작업으로」 가 갈린다 — 기본은 덮어 저장', async () => {
  const calls = mockApi()
  render(
    <MemoryRouter initialEntries={['/draw']}>
      <Routes>
        <Route path="/draw" element={<DrawPage />} />
        <Route path="/works/:id" element={<div>작업 화면</div>} />
      </Routes>
    </MemoryRouter>,
  )
  await loadExisting()
  fireEvent.mouseDown(screen.getByRole('tab', { name: '파일' })) // 불러오면 스케치 탭으로 간다
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  expect(await screen.findByText(/「센서 브래킷」 에 덮어 저장/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /^새 작업으로 저장/ })).toBeInTheDocument()

  // 덮어 저장 = 그 작업에 새 버전. 새 작업은 만들지 않는다.
  fireEvent.click(screen.getByRole('button', { name: '「센서 브래킷」 에 저장' }))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/works/w1/versions'))).toBe(true))
  expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/works'))).toBe(false)
})

test('처음부터 그린 것은 새 작업으로만 저장된다', async () => {
  mockApi()
  render(
    <MemoryRouter initialEntries={['/draw']}>
      <Routes>
        <Route path="/draw" element={<DrawPage />} />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.mouseDown(screen.getByRole('tab', { name: '입체' }))
  fireEvent.click(screen.getByRole('button', { name: /^블록/ }))
  fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  fireEvent.mouseDown(screen.getByRole('tab', { name: '파일' }))
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  expect(await screen.findByLabelText('작업 이름')).toBeInTheDocument()
  expect(screen.queryByText(/덮어 저장/)).toBeNull()
})

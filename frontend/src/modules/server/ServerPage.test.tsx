import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import ServerPage from '@/modules/server/ServerPage'

test('워커 — 응답 없는 워커와, 살아 있는 워커 없이 줄이 선 것을 크게 말한다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/server/workers')
      ? {
          alive: 0,
          queue: { queued: 3, running: 1, cancelling: 1, oldest_queued_seconds: 600 },
          workers: [
            {
              id: 'jig-01:4242',
              hostname: 'jig-01',
              pid: 4242,
              version: '0.6.0',
              state: 'lost',
              started_at: '2026-10-03T00:00:00Z',
              last_seen_at: '2026-10-03T00:00:00Z',
              silent_seconds: 300,
              job: null,
            },
          ],
        }
      : url.endsWith('/server/settings')
        ? []
        : url.endsWith('/server/shape-index')
          ? { missing: 0 }
          : null
    if (body === null) {
      // 서버 상태는 이 시험의 일이 아니다 — 오류여도 워커 카드는 따로 떠야 한다.
      return new Response(JSON.stringify({ error: { code: 'X', message: '없음' } }), { status: 500, headers: { 'Content-Type': 'application/json' } })
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<ServerPage />)
  expect(await screen.findByText(/살아 있는 워커가 없는데 작업 3 개가 기다립니다/)).toBeInTheDocument()
  expect(screen.getByText('응답 없음')).toBeInTheDocument()
  expect(screen.getByText('5분 전')).toBeInTheDocument()
  expect(screen.getByText(/가장 오래 기다린 것 10분 전 걸림/)).toBeInTheDocument()
})

test('형상 색인 — 없는 것을 세고, 다 될 때까지 이어서 채운다', async () => {
  let missing = 30
  const posts: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
    if (url.includes('/server/shape-index') && init?.method === 'POST') {
      posts.push(url)
      const done = Math.min(20, missing)
      missing -= done
      return json({ filled: done, failed: 0, remaining: missing })
    }
    if (url.endsWith('/server/shape-index')) return json({ missing })
    if (url.endsWith('/server/workers')) return json({ alive: 1, queue: { queued: 0, running: 0, cancelling: 0, oldest_queued_seconds: null }, workers: [] })
    if (url.endsWith('/server/settings')) return json([])
    return json({ error: { code: 'X', message: '없음' } }, 500)
  })
  render(<ServerPage />)
  expect(await screen.findByText(/색인이 없는 최신 버전/)).toHaveTextContent('30 개')
  fireEvent.click(screen.getByRole('button', { name: '형상 색인 채우기' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('채움 30 · 남음 0'))
  expect(posts).toHaveLength(2)
  expect(await screen.findByText(/모든 최신 버전에 색인이 있습니다/)).toBeInTheDocument()
})

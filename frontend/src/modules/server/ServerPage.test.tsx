import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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
  expect(await screen.findByText(/실행 중인 워커가 없어 작업 3개가 대기 중입니다/)).toBeInTheDocument()
  expect(screen.getByText('응답 없음')).toBeInTheDocument()
  expect(screen.getByText('5분 전')).toBeInTheDocument()
  expect(screen.getByText(/가장 오래된 대기 작업: 10분 전 요청/)).toBeInTheDocument()
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
  expect(await screen.findByText(/색인이 없는 최신 버전/)).toHaveTextContent('30개')
  fireEvent.click(screen.getByRole('button', { name: '형상 색인 생성' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('완료 30 · 잔여 0'))
  expect(posts).toHaveLength(2)
  expect(await screen.findByText(/모든 최신 버전에 색인이 있습니다/)).toBeInTheDocument()
})

test('판금 굽힘 점검 — 모양이 바뀌는 판금과 이제 생성되지 않는 판금을 나눠 보여 준다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/server/bend-check')
      ? {
          scanned: 3,
          failing: 1,
          truncated: false,
          items: [
            { kind: 'work', id: 'w1', name: '브래킷', owner: '김', version: 2, node: '판', bends: 1, status: 'changed', error: '' },
            { kind: 'doe', id: 'd1', name: '두께 탐색', owner: '이', version: null, node: '판', bends: 1, status: 'failing', error: '판: 판을 굽히지 못했습니다.' },
          ],
        }
      : url.endsWith('/server/settings')
        ? []
        : url.endsWith('/server/shape-index')
          ? { missing: 0 }
          : url.endsWith('/server/workers')
            ? { alive: 1, queue: { queued: 0, running: 0, cancelling: 0, oldest_queued_seconds: null }, workers: [] }
            : null
    if (body === null) {
      return new Response(JSON.stringify({ error: { code: 'X', message: '없음' } }), { status: 500, headers: { 'Content-Type': 'application/json' } })
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter>
      <ServerPage />
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByRole('button', { name: '점검' }))
  expect(await screen.findByRole('link', { name: '브래킷' })).toHaveAttribute('href', '/works/w1')
  expect(screen.getByText('모양 변경')).toBeInTheDocument()
  expect(screen.getByText(/생성 실패: 판: 판을 굽히지 못했습니다/)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('모양이 바뀌는 판금 노드 2개(이 중 생성 실패 1개)')
})

test('해석 쪽 능력표 — 받은 솔버와 판을 보이고, 갱신이 실패하면 서버가 말한 고칠 것을 그대로 띄운다', async () => {
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  const status = {
    configured: true,
    missing: '',
    base_url: 'https://seb.example/simengbay',
    source: '',
    fetched_at: null,
    tables: null,
  }
  let refreshes = 0
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/server/capabilities/refresh') && init?.method === 'POST') {
      refreshes += 1
      if (refreshes === 1) {
        return json(
          {
            ...status,
            source: status.base_url,
            fetched_at: '2026-11-27T04:00:00Z',
            tables: [
              { solver: 'calculix', version: null, receiver_version: 'v0.36.0', analyses: { modal: {}, static: {} } },
              { solver: 'ansys', version: '2025 R2', receiver_version: 'v0.36.0', analyses: { random: {} } },
            ],
          },
        )
      }
      return json({ error: { code: 'CCR-SERVER-0003', message: 'SimEngBay 토큰에 읽기 범위(read)가 없습니다.' } }, 502)
    }
    if (url.endsWith('/server/capabilities')) return json(status)
    if (url.endsWith('/server/workers')) return json({ alive: 1, queue: { queued: 0, running: 0, cancelling: 0, oldest_queued_seconds: null }, workers: [] })
    if (url.endsWith('/server/settings')) return json([])
    if (url.endsWith('/server/shape-index')) return json({ missing: 0 })
    return json({ error: { code: 'X', message: '없음' } }, 500)
  })
  render(<ServerPage />)
  expect(await screen.findByText('아직 받은 능력표가 없어 대상 솔버로 확인하지 않습니다.')).toBeInTheDocument()
  expect(screen.getByText('받은 적 없음')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '갱신' }))
  expect(await screen.findByText('2025 R2')).toBeInTheDocument()
  expect(screen.getByText('알 수 없음')).toBeInTheDocument()
  expect(screen.getByText('모달, 정적 구조')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '갱신' }))
  expect(await screen.findByText(/읽기 범위\(read\)가 없습니다/)).toBeInTheDocument()
  // 실패해도 받아 둔 표는 그대로 보인다.
  expect(screen.getByText('2025 R2')).toBeInTheDocument()
})

test('해석 쪽 능력표 — .env 가 비면 무엇이 비었는지 말하고 갱신을 막는다', async () => {
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/server/capabilities')) {
      return json({ configured: false, missing: '.env에 SIMENGBAY_TOKEN(토큰) 값이 설정되지 않았습니다.', base_url: '', source: '', fetched_at: null, tables: null })
    }
    if (url.endsWith('/server/settings')) return json([])
    return json({ error: { code: 'X', message: '없음' } }, 500)
  })
  render(<ServerPage />)
  expect(await screen.findByText(/SIMENGBAY_TOKEN\(토큰\) 값이 설정되지 않았습니다/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '갱신' })).toBeDisabled()
})

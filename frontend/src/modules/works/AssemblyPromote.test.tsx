import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorkPage from '@/modules/works/WorkPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

// 공용 조립(2026-11-17) — 조립 작업에도 등록 단추가 있고, 무엇이 함께 공용으로 나가는지 보고 누른다.

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }

const WORK = {
  id: 'w1',
  name: '판 + 받침',
  owner_id: 'u1',
  owner_name: '나',
  description: '',
  kind: 'assembly',
  jig_for_part_id: null,
  jig_for_part_name: null,
  current_version: 1,
  jig_run_count: 0,
  current: {
    number: 1,
    recipe: {
      nodes: [
        { id: '받침', op: 'component', source: 'part:p1' },
        { id: '판', op: 'component', source: 'work:w2' },
      ],
    },
    job: { status: 'done', artifacts: [], progress: [] },
    promoted_part_id: null,
  },
  jig_options: {},
  promoted_part_id: null,
  promoted_jig_id: null,
  tags: [],
  deleted_at: null,
}

const PLAN = {
  components: [
    { node: '받침', label: '받침', kind: 'part', name: '받침', action: 'pin', source: 'part:p1', target: 'part:p1@1', version: 1 },
    { node: '판', label: '판', kind: 'part', name: '판', action: 'register', source: 'work:w2', target: null, version: 1 },
  ],
}

type Sent = { method: string; url: string; body?: Record<string, unknown> }

function serve() {
  const sent: Sent[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    sent.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    let status = 200
    let body: unknown
    if (url.endsWith('/auth/refresh')) body = { access_token: 't', expires_in: 900, user: ME }
    else if (url.endsWith('/promote/assembly') && method === 'GET') body = PLAN
    else if (url.endsWith('/promote/assembly')) {
      status = 201
      body = { part_id: 'p9', part_version: 1, components: PLAN.components }
    } else if (url.includes('/works/w1/versions')) body = [WORK.current]
    else if (url.includes('/works/w1/jig-runs')) body = []
    else if (url.includes('/works/tags') || url.includes('/works/folders')) body = []
    else if (url.includes('/works/w1')) body = WORK
    else body = { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return sent
}

function show() {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/works/w1']}>
        <Routes>
          <Route path="/works/:id" element={<WorkPage />} />
          <Route path="/assemblies/:id" element={<p>공용 조립 화면</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('조립은 공용 조립으로 등록하고, 함께 등록될 구성품을 먼저 보인다', async () => {
  const sent = serve()
  show()
  fireEvent.click(await screen.findByRole('button', { name: '공용 조립으로 등록' }))
  const plan = await screen.findByRole('list', { name: '구성품 등록 계획' })
  expect(within(plan).getByText('부품 · 공용 · 현재 버전으로 고정 (v1)')).toBeInTheDocument()
  expect(within(plan).getByText('부품 · 함께 등록 (v1)')).toBeInTheDocument()
  expect(screen.getByText(/공용에 없는 구성품 1개\(판\)가 공용 부품 · 지그로 함께 등록되어/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('카탈로그 이름'), { target: { value: '공용 판 조립' } })
  fireEvent.click(screen.getByRole('button', { name: '등록' }))
  expect(await screen.findByText('공용 조립 화면')).toBeInTheDocument()
  const posted = sent.find((one) => one.method === 'POST' && one.url.endsWith('/promote/assembly'))
  expect(posted?.body).toMatchObject({ name: '공용 판 조립' })
  // 부품으로 올리는 길은 타지 않는다 — 조립의 `work:` 참조가 그대로 나가면 남이 못 연다.
  expect(sent.some((one) => one.url.endsWith('/promote/part'))).toBe(false)
})

test('이미 등록한 버전이면 단추가 잠기고 공용 조립으로 가는 링크가 보인다', async () => {
  serve()
  vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
    const url = String(input)
    const done = { ...WORK, promoted_part_id: 'p9', current: { ...WORK.current, promoted_part_id: 'p9', promoted_part_version: 1 } }
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.includes('/works/w1/versions')
        ? [done.current]
        : url.includes('/works/w1/jig-runs') || url.includes('/works/tags') || url.includes('/works/folders')
          ? []
          : url.includes('/works/w1')
            ? done
            : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  show()
  await waitFor(() => expect(screen.getByRole('button', { name: '조립 v1 등록됨' })).toBeDisabled())
  expect(screen.getByRole('link', { name: '조립으로 등록됨' })).toHaveAttribute('href', '/assemblies/p9')
})

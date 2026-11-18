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

// 평가가 없는 구성품(2026-11-18) — 그 전에는 「그 작업을 열어 다시 저장하라」 며 막혔다. 이제 등록 창이 평가를 걸고 기다려 잇는다.
const MISSING = { work_id: 'w2', name: '판', label: '판', version: 1, status: 'missing', job_id: null, error: null }

/** 계획(GET) · 평가(POST evaluate) 의 답을 차례로 준다 — 마지막 것은 되풀이. */
function serveEvaluations(plans: unknown[][], evaluated: unknown[]) {
  const sent: Sent[] = []
  let gets = 0
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    sent.push({ method, url })
    let status = 200
    let body: unknown
    if (url.endsWith('/auth/refresh')) body = { access_token: 't', expires_in: 900, user: ME }
    else if (url.endsWith('/promote/assembly/evaluate')) body = { components: PLAN.components, evaluations: evaluated }
    else if (url.endsWith('/promote/assembly') && method === 'GET') {
      body = { components: PLAN.components, evaluations: plans[Math.min(gets, plans.length - 1)] }
      gets += 1
    } else if (url.endsWith('/promote/assembly')) {
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

test('평가가 없는 구성품은 「평가하고 등록」 이 평가를 걸고 끝나기를 기다려 등록한다', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    // 처음 계획: 평가 없음 → 걸면 평가 중 → 다시 보면 끝(빈 목록).
    const sent = serveEvaluations([[MISSING], []], [{ ...MISSING, status: 'running', job_id: 'j1' }])
    show()
    fireEvent.click(await screen.findByRole('button', { name: '공용 조립으로 등록' }))
    const pending = await screen.findByRole('list', { name: '구성품 평가' })
    expect(within(pending).getByText('평가 없음')).toBeInTheDocument()
    expect(screen.getByText(/형상 평가가 끝나지 않은 구성품 1개/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '평가하고 등록' }))
    expect(await screen.findByRole('button', { name: '구성품 평가 중…' })).toBeDisabled()
    expect(within(screen.getByRole('list', { name: '구성품 평가' })).getByText('평가 중')).toBeInTheDocument()
    await vi.advanceTimersByTimeAsync(2500)
    expect(await screen.findByText('공용 조립 화면')).toBeInTheDocument()
    const order = sent.filter((one) => one.url.includes('/promote/assembly')).map((one) => `${one.method} ${one.url.split('/promote/')[1]}`)
    expect(order).toEqual(['GET assembly', 'POST assembly/evaluate', 'GET assembly', 'POST assembly'])
  } finally {
    vi.useRealTimers()
  }
})

test('구성품 평가가 실패하면 등록하지 않고 까닭을 창 안에 보인다', async () => {
  const failed = { ...MISSING, status: 'failed', job_id: 'j1', error: '구성품 ‘볼트’를 찾을 수 없습니다.' }
  const sent = serveEvaluations([[MISSING]], [failed])
  show()
  fireEvent.click(await screen.findByRole('button', { name: '공용 조립으로 등록' }))
  fireEvent.click(await screen.findByRole('button', { name: '평가하고 등록' }))
  // 까닭은 창 안에 — 창 뒤의 화면에만 두면 안 보인다.
  expect(await within(screen.getByRole('dialog')).findByText(/구성품 ‘판’\(판 v1\)의 형상 평가가 실패했습니다: 구성품 ‘볼트’를 찾을 수 없습니다/)).toBeInTheDocument()
  expect(within(screen.getByRole('list', { name: '구성품 평가' })).getByText('평가 실패')).toBeInTheDocument()
  expect(sent.some((one) => one.method === 'POST' && one.url.endsWith('/promote/assembly'))).toBe(false)
})

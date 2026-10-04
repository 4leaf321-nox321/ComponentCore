import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import WorkPage from '@/modules/works/WorkPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: true, must_change_password: false }

const WORK = {
  id: 'w1',
  name: '튜닝 지그',
  owner_id: 'u1',
  owner_name: '나',
  description: '',
  kind: 'jig',
  jig_for_part_id: null,
  jig_for_part_name: null,
  current_version: 2,
  jig_run_count: 0,
  current: { number: 2, recipe: { params: { 두께: 6 }, nodes: [] }, job: { status: 'done', artifacts: [], progress: [] } },
  jig_options: {},
  promoted_part_id: null,
  promoted_jig_id: null,
  tags: [],
  deleted_at: null,
}

function serve(work: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.endsWith('/promote/part')
        ? { part_id: 'p1', number: 1 }
      : url.endsWith('/promote/jig-recipe')
        ? { jig_id: 'j1', jig_version: 1 }
      : url.endsWith('/api/doe')
        ? { id: 'd1', name: '튜닝 지그 해석' }
      : url.includes('/works/w1/versions')
      ? [WORK.current]
      : url.includes('/works/w1/jig-runs')
        ? []
        : url.includes('/works/jig-options')
          ? {}
          : url.includes('/works/tags') || url.includes('/works/folders')
            ? []
            : url.includes('/works/w1')
              ? work
              : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}

function show() {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/works/w1']}>
        <Routes>
          <Route path="/works/:id" element={<WorkPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('지그 작업은 그림 탭이 「지그」 이고, 승격이 지그 카탈로그로 간다', async () => {
  serve(WORK)
  show()
  // 그림 탭 이름은 종류와 상관없이 「도면」 — 생성기 탭은 이제 어느 작업에도 없다(새 작업 › 부품에서 지그 생성).
  await waitFor(() => expect(screen.getByRole('tab', { name: /^도면$/ })).toBeInTheDocument())
  expect(screen.queryByRole('tab', { name: /지그 만들어 주기/ })).toBeNull()
  expect(await screen.findByRole('button', { name: '공용 지그로 등록' })).toBeInTheDocument()
})

test('관리자가 남의 작업을 열면 누구의 것인지 늘 보이고, 꼬리표 제안도 그 사람의 것', async () => {
  serve({ ...WORK, owner_id: 'kim', owner_name: '김' })
  const calls = vi.mocked(globalThis.fetch).mock.calls
  show()
  const note = await screen.findByRole('note')
  expect(note).toHaveTextContent('김의 작업입니다')
  expect(screen.getByRole('link', { name: /모든 작업/ })).toHaveAttribute('href', '/admin/works?owner=kim')
  await waitFor(() => expect(calls.some(([url]) => String(url).includes('/works/tags?owner=kim'))).toBe(true))
})

test('내 작업이면 알림이 없다', async () => {
  serve(WORK)
  show()
  expect(await screen.findByRole('button', { name: '공용 지그로 등록' })).toBeInTheDocument()
  expect(screen.queryByRole('note')).toBeNull()
})

test('해석용으로 내보내기 — 변수 없이 지금 설계 하나인 DOE 를 만든다', async () => {
  serve(WORK)
  show()
  fireEvent.click(await screen.findByRole('button', { name: '해석용으로 내보내기' }))
  expect(screen.getByLabelText('이름')).toHaveValue('튜닝 지그 해석')
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  const calls = vi.mocked(globalThis.fetch).mock.calls
  await waitFor(() => expect(calls.some(([url, init]) => String(url).endsWith('/api/doe') && init?.method === 'POST')).toBe(true))
  const [, init] = calls.find(([url, one]) => String(url).endsWith('/api/doe') && one?.method === 'POST')!
  const body = JSON.parse(String(init?.body))
  expect(body).toMatchObject({ name: '튜닝 지그 해석', factors: [], work_id: 'w1' })
  expect(body.recipe).toEqual(WORK.current.recipe)
})

test('부품으로 등록할 때 해석 조건을 함께 올리고, 해제하면 형상만 올린다', async () => {
  const conditions = { constraints: [{ name: '고정', type: 'fixed_support', on: '바닥' }] }
  serve({ ...WORK, kind: 'part', current: { ...WORK.current, conditions } })
  show()
  fireEvent.click(await screen.findByRole('button', { name: '공용 부품으로 등록' }))
  const box = screen.getByRole('checkbox', { name: /해석 조건도 함께 등록/ })
  expect(box).toBeChecked()
  fireEvent.click(box)
  fireEvent.click(screen.getByRole('button', { name: '등록' }))
  const calls = vi.mocked(globalThis.fetch).mock.calls
  await waitFor(() => expect(calls.some(([url]) => String(url).endsWith('/promote/part'))).toBe(true))
  const [, init] = calls.find(([url]) => String(url).endsWith('/promote/part'))!
  expect(JSON.parse(String(init?.body))).toMatchObject({ conditions: false })
})

test('조건이 없는 작업은 묻지 않는다', async () => {
  serve({ ...WORK, kind: 'part' })
  show()
  fireEvent.click(await screen.findByRole('button', { name: '공용 부품으로 등록' }))
  expect(screen.queryByRole('checkbox', { name: /해석 조건도 함께 등록/ })).toBeNull()
})

test('지그로 등록할 때도 해석 조건을 함께 올린다', async () => {
  const conditions = { loads: [{ name: '누름', type: 'pressure', on: '윗면', magnitude: 1 }] }
  serve({ ...WORK, current: { ...WORK.current, conditions } })
  show()
  fireEvent.click(await screen.findByRole('button', { name: '공용 지그로 등록' }))
  expect(screen.getByRole('checkbox', { name: /해석 조건도 함께 등록/ })).toBeChecked()
  expect(screen.getByText(/이 지그를 복사한 사용자가/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '등록' }))
  const calls = vi.mocked(globalThis.fetch).mock.calls
  await waitFor(() => expect(calls.some(([url]) => String(url).endsWith('/promote/jig-recipe'))).toBe(true))
  const [, init] = calls.find(([url]) => String(url).endsWith('/promote/jig-recipe'))!
  expect(JSON.parse(String(init?.body))).toMatchObject({ conditions: true })
})

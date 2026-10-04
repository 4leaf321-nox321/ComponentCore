/**
 * **내 것으로 복제** — 남의 DOE 는 보기만 되고, 이어서 하려는 사람은 같은 설계점 · 조건으로
 * 자기 DOE 를 갖는다. 소유자에게만 되는 단추(보내기 · 점 추가 …)는 남에게 보이지 않는다.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import DoeStudyPage from '@/modules/doe/DoeStudyPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

vi.mock('@/shared/viewer/PickViewer', () => ({ default: () => <div data-testid="viewer" /> }))
vi.mock('@/shared/viewer/GridViewer', () => ({ GridViewer: () => <div data-testid="grid" /> }))

const ME = { id: 'u2', email: 'lee@x', display_name: '이해석', status: 'active', is_system_admin: false, must_change_password: false }

const STUDY = {
  id: 's1',
  name: '두께 훑기',
  description: '',
  work_id: 'w1',
  work_name: '판',
  work_kind: 'part',
  method: 'factorial',
  samples: 2,
  seed: 1,
  point_count: 2,
  created_at: '2026-10-04T00:00:00Z',
  owner_id: 'u1',
  owner_name: '김설계',
  visibility: 'read',
  cloned_from_id: null,
  cloned_from_name: '',
  recipe: { nodes: [] },
  conditions: {},
  factors: [{ name: '두께', mode: 'list', values: [2, 4] }],
  done: 2,
  failed: 0,
  local_ready: true,
  requested_by_name: '',
  job: { status: 'done', artifacts: [], progress: [] },
  export_dir_windows: '',
  exported_at: null,
  points: [
    { id: 'a', number: 1, params: { 두께: 2 }, status: 'ok', error: '', step_file: 'points/p0001.step' },
    { id: 'b', number: 2, params: { 두께: 4 }, status: 'ok', error: '', step_file: 'points/p0002.step' },
  ],
}

function serve(study: Record<string, unknown>) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, init })
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.endsWith('/doe/s1/clone')
        ? { ...study, id: 's2', name: '두께 훑기 (복제)', owner_id: 'u2', owner_name: '이해석', cloned_from_id: 's1', cloned_from_name: '두께 훑기' }
        : url.endsWith('/doe/s2')
          ? { ...study, id: 's2', name: '두께 훑기 (복제)', owner_id: 'u2', owner_name: '이해석', cloned_from_id: 's1', cloned_from_name: '두께 훑기' }
          : url.endsWith('/doe/s1')
            ? study
            : url.includes('/server/display')
              ? { doe_gallery_max: 24, list_page_size: 20 }
              : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/doe/s1']}>
        <Routes>
          <Route path="/doe/:id" element={<DoeStudyPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
  return calls
}

test('남의 DOE 는 보기만 되고, 내 것으로 복제하면 내 DOE 로 간다', async () => {
  const calls = serve(STUDY)
  expect(await screen.findByRole('note')).toHaveTextContent('김설계의 DOE입니다')
  // 소유자만 되는 단추는 없다 — 눌러도 서버가 막는다.
  expect(screen.queryByRole('button', { name: /공유 폴더로 내보내기/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /설계점 추가/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /설정 변경 후 새 DOE 생성/ })).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: '내 것으로 복제' }))
  expect(screen.getByLabelText('이름')).toHaveValue('두께 훑기 (복제)')
  fireEvent.click(screen.getByRole('button', { name: '복제' }))
  await waitFor(() => expect(calls.some((one) => one.url.endsWith('/doe/s1/clone') && one.init?.method === 'POST')).toBe(true))
  // 복제본 — 원본을 가리키고, 내 것이니 고치는 단추가 있다.
  expect(await screen.findByRole('link', { name: '‘두께 훑기’' })).toHaveAttribute('href', '/doe/s1')
  expect(await screen.findByRole('button', { name: /설계점 추가/ })).toBeInTheDocument()
  expect(screen.queryByRole('note')).toBeNull()
})

test('내 DOE 에는 고치는 단추와 복제가 함께 있다', async () => {
  serve({ ...STUDY, owner_id: 'u2', owner_name: '이해석' })
  expect(await screen.findByRole('button', { name: /공유 폴더로 내보내기/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '복제' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /설정 변경 후 새 DOE 생성/ })).toBeInTheDocument()
  expect(screen.queryByRole('note')).toBeNull()
})

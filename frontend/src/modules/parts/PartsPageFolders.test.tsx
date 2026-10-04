import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import JigsPage from '@/modules/jigs/JigsPage'
import PartsPage from '@/modules/parts/PartsPage'
import { AuthProvider } from '@/shared/auth/AuthContext'
import { josa } from '@/shared/folders/paths'

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }

const part = (id: string, name: string, owner: string, folder: string) => ({
  id,
  name,
  description: '',
  owner_id: owner,
  owner_name: owner === 'u1' ? '나' : '동료',
  current_version: 1,
  jig_count: 0,
  interference_ok: null,
  part_id: null,
  part_name: null,
  tags: [],
  folder,
  updated_at: '2026-09-20T00:00:00Z',
})

/** 부품 · 지그 카탈로그가 같은 모양으로 답한다. */
function mockCatalog(base: 'parts' | 'jigs') {
  const calls: { method: string; url: string; body?: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method: init?.method ?? 'GET', url, body })
    const u = new URL(url, 'http://x')
    let out: unknown
    if (u.pathname.endsWith('/auth/refresh')) out = { access_token: 't', expires_in: 900, user: ME }
    else if (u.pathname.endsWith(`/${base}/tags`)) out = []
    else if (u.pathname.endsWith(`/${base}/folders`))
      out = [
        { path: '', count: 0 },
        { path: '공정', count: 1 },
        { path: '공정/선반', count: 1 },
      ]
    else if (u.pathname.endsWith(`/${base}/move`)) out = { moved: 1 }
    else if (u.pathname.endsWith(`/${base}`)) {
      const all = [part('p1', '내 브래킷', 'u1', '공정/선반'), part('p2', '남의 블록', 'u2', '공정')]
      const folder = u.searchParams.get('folder')
      const items = folder === null ? all : all.filter((one) => one.folder === folder || one.folder.startsWith(`${folder}/`))
      out = { items, total: items.length, limit: 20, offset: 0 }
    } else out = {}
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

test('부품 카탈로그 — 폴더로 거르고, 내 것만 골라 옮긴다', async () => {
  const calls = mockCatalog('parts')
  render(
    <AuthProvider>
      <MemoryRouter>
        <PartsPage />
      </MemoryRouter>
    </AuthProvider>,
  )
  expect(await screen.findByText('남의 블록')).toBeInTheDocument()
  const tree = screen.getByRole('navigation', { name: '폴더' })
  // 「공정」 은 하위까지 합쳐 2.
  expect(within(tree).getByText('공정').closest('button')).toHaveTextContent('2')

  // 남의 부품은 고르지 못한다 — 옮기는 것은 올린 사람 · 관리자.
  await waitFor(() => expect(screen.getByLabelText('내 브래킷 선택')).not.toBeDisabled())
  expect(screen.getByLabelText('남의 블록 선택')).toBeDisabled()

  fireEvent.click(within(tree).getByText('선반'))
  await waitFor(() => expect(screen.queryByText('남의 블록')).toBeNull())
  expect(calls.some((one) => one.url.includes('folder=%EA%B3%B5%EC%A0%95%2F%EC%84%A0%EB%B0%98'))).toBe(true)

  fireEvent.click(screen.getByLabelText('내 브래킷 선택'))
  fireEvent.click(screen.getByRole('button', { name: '폴더로 이동' }))
  fireEvent.change(screen.getByLabelText('폴더 경로'), { target: { value: ' 보관 / 2026' } })
  fireEvent.click(screen.getByRole('button', { name: '이동' }))
  await waitFor(() => expect(calls.some((one) => one.url.endsWith('/parts/move'))).toBe(true))
  expect(calls.find((one) => one.url.endsWith('/parts/move'))?.body).toEqual({ ids: ['p1'], folder: '보관/2026' })
})

test('지그 카탈로그 — 폴더 없음은 하위를 보지 않고, 폴더 이름 바꾸기는 서버에 묻는다', async () => {
  const calls = mockCatalog('jigs')
  render(
    <AuthProvider>
      <MemoryRouter>
        <JigsPage />
      </MemoryRouter>
    </AuthProvider>,
  )
  expect(await screen.findByText('내 브래킷')).toBeInTheDocument()
  const tree = screen.getByRole('navigation', { name: '폴더' })
  fireEvent.click(within(tree).getByText('폴더 없음'))
  await waitFor(() => expect(calls.some((one) => one.url.includes('folder=&') && one.url.includes('subfolders=false'))).toBe(true))

  fireEvent.click(within(tree).getByLabelText('공정 이름 변경'))
  // 여럿이 쓰는 공간 — 남의 것이 든 폴더는 관리자만이라고 적는다.
  expect(screen.getByText(/다른 사용자의 지그가 포함된 폴더는 관리자만/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('폴더 경로'), { target: { value: '가공' } })
  fireEvent.click(screen.getByRole('button', { name: '변경' }))
  await waitFor(() => expect(calls.some((one) => one.url.endsWith('/jigs/folders/rename'))).toBe(true))
  expect(calls.find((one) => one.url.endsWith('/jigs/folders/rename'))?.body).toEqual({ path: '공정', to: '가공' })
})

test('이름 뒤 조사는 받침을 본다', () => {
  expect(josa('부품', '을', '를')).toBe('부품을')
  expect(josa('지그', '을', '를')).toBe('지그를')
  expect(josa('템플릿', '이', '가')).toBe('템플릿이')
  expect(josa('작업', '은', '는')).toBe('작업은')
})

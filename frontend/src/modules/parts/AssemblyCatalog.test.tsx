import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import PartPage from '@/modules/parts/PartPage'
import PartsPage from '@/modules/parts/PartsPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

// 공용 조립(2026-11-17) — 부품 카탈로그의 `kind='assembly'`. 목록 · 상세가 부품 화면을 같이 쓴다.

const ME = { id: 'u2', email: 'kim@x', display_name: '김', status: 'active', is_system_admin: false, must_change_password: false }

const VERSION = {
  id: 'pv1',
  part_id: 'a1',
  number: 1,
  recipe: {
    nodes: [
      { id: '받침', op: 'component', source: 'part:p1@1' },
      { id: '시험 지그', op: 'component', source: 'jig:j1@2' },
      { id: '조립', op: 'group', targets: ['받침', '시험 지그'] },
    ],
  },
  conditions: {},
  job: null,
  note: '',
  promoted_by_id: 'u1',
  promoted_by_name: '나',
  work_version_id: null,
  created_at: '2026-11-17T00:00:00Z',
}

const ASSEMBLY = {
  id: 'a1',
  name: '판 + 받침',
  kind: 'assembly',
  tags: [],
  description: '',
  owner_id: 'u1',
  owner_name: '나',
  work_id: null,
  current_version: 1,
  version_count: 1,
  current: VERSION,
  jig_count: 0,
  folder: '',
  created_at: '2026-11-17T00:00:00Z',
  updated_at: '2026-11-17T00:00:00Z',
}

function serve() {
  const urls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    urls.push(url)
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: ME }
      : url.includes('/parts/folders')
        ? [{ path: '', count: 1 }]
        : url.endsWith('/parts/a1/versions')
          ? [VERSION]
          : url.endsWith('/parts/a1')
            ? ASSEMBLY
            : url.includes('/parts?')
              ? { items: [ASSEMBLY], total: 1, limit: 50, offset: 0 }
              : url.includes('/tags')
                ? []
                : { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return urls
}

function show(path: string) {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/assemblies" element={<PartsPage kind="assembly" />} />
          <Route path="/assemblies/:id" element={<PartPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('조립 목록은 조립만 묻고, 부품에만 뜻이 있는 칸은 뺀다', async () => {
  const urls = serve()
  show('/assemblies')
  const link = await screen.findByRole('link', { name: '판 + 받침' })
  expect(link).toHaveAttribute('href', '/assemblies/a1')
  expect(urls.some((one) => one.includes('/parts?') && one.includes('kind=assembly'))).toBe(true)
  await waitFor(() => expect(urls.some((one) => one.includes('/parts/folders?kind=assembly'))).toBe(true))
  expect(screen.getByRole('heading', { name: '조립' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '규격 부품' })).toBeNull()
  expect(screen.queryByRole('columnheader', { name: '지그' })).toBeNull()
})

test('공용 조립은 고정된 구성품을 그 카탈로그로 잇는다', async () => {
  serve()
  show('/assemblies/a1')
  const list = await screen.findByRole('list', { name: '구성품' })
  expect(within(list).getByRole('link', { name: '받침' })).toHaveAttribute('href', '/parts/p1')
  expect(within(list).getByRole('link', { name: '시험 지그' })).toHaveAttribute('href', '/jigs/j1')
  expect(within(list).getByText('지그 v2')).toBeInTheDocument()
  // 부품에만 있는 칸은 없다 — 이 부품의 지그 · 규격 사양.
  expect(screen.queryByText('이 부품의 지그')).toBeNull()
  expect(screen.getByRole('link', { name: '조립' })).toHaveAttribute('href', '/assemblies')
})

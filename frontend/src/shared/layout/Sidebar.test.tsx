import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '@/shared/auth/AuthContext'
import { Sidebar } from '@/shared/layout/Sidebar'

// 접힘은 브라우저에 남는다 — 앞 시험이 접은 묶음이 뒤 시험에 새지 않게.
afterEach(() => window.localStorage.clear())

interface Served {
  summary?: Record<string, unknown>
  nav?: unknown[]
  me?: Record<string, unknown>
}

function serve({ summary = { waiting: 0, to_confirm: 0 }, nav = [], me: extra = {} }: Served) {
  const asked: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    asked.push(url)
    const me = {
      id: 'u1',
      email: 'me@x',
      display_name: '나',
      status: 'active',
      is_system_admin: true,
      must_change_password: false,
      memberships: [],
      home_workspace_slug: null,
      ...extra,
    }
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: me }
      : url.endsWith('/voc/summary')
        ? summary
        : url.endsWith('/ontology/nav')
          ? nav
          : { status: 'ok', version: 'v0.13.0', app: 'CompCore' }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter>
        <Sidebar collapsed={false} workspaceSlug={(extra.home_workspace_slug as string | undefined) ?? null} />
      </MemoryRouter>
    </AuthProvider>,
  )
  return asked
}

test('손댈 차례인 VOC 가 없으면 숫자를 그리지 않는다', async () => {
  const asked = serve({ summary: { waiting: 0, to_confirm: 0 } })
  await waitFor(() => expect(asked.some((one) => one.endsWith('/voc/summary'))).toBe(true))
  expect(screen.getByRole('link', { name: /VOC/ })).toBeInTheDocument()
  expect(screen.queryByLabelText(/대기/)).toBeNull()
})

test('VOC 메뉴 옆에 접수 대기와 확인 대기를 더해 센다', async () => {
  serve({ summary: { waiting: 2, to_confirm: 1 } })
  const badge = await screen.findByLabelText('접수 대기 2건, 확인 대기 1건')
  expect(badge).toHaveTextContent('3')
  expect(screen.getByRole('link', { name: /VOC/ })).toContainElement(badge)
})

test('온톨로지가 준 묶음이 기준정보 앞에 서고, 기록 타입에는 표가 붙는다', async () => {
  serve({
    nav: [
      {
        slug: 'master',
        label: '제품 기준정보',
        icon: 'package',
        audience: 'everyone',
        parent: null,
        items: [
          { label: '제품', icon: 'package', to: '/o/product', slug: 'product', usage: 'axis' },
          { label: '시험 기록', icon: 'flask', to: '/o/test-log', slug: 'test-log', usage: 'log' },
        ],
      },
    ],
  })
  const product = await screen.findByRole('link', { name: /제품$/ })
  expect(product).toHaveAttribute('href', '/o/product')
  expect(screen.getByRole('link', { name: /시험 기록/ })).toHaveTextContent('기록')
  const titles = screen.getAllByRole('button').map((one) => one.textContent)
  expect(titles.indexOf('제품 기준정보')).toBeLessThan(titles.indexOf('기준정보'))
})

test('소속 부서가 없으면 부서 스코프 항목이 안 서고, 있으면 그 부서를 가리킨다', async () => {
  serve({})
  await screen.findByRole('link', { name: /변경 이력/ })
  expect(screen.queryByRole('link', { name: /부서 홈/ })).toBeNull()
})

test('소속 부서가 있으면 부서 홈이 그 부서를 가리킨다', async () => {
  serve({
    me: {
      home_workspace_slug: 'cae',
      memberships: [{ workspace_id: 'w1', slug: 'cae', name: 'CAE', path: 'CAE', role: 'manager' }],
    },
  })
  expect(await screen.findByRole('link', { name: /부서 홈/ })).toHaveAttribute('href', '/w/cae')
})

test('묶음을 접으면 그 안의 링크를 그리지 않는다', async () => {
  serve({})
  const title = await screen.findByRole('button', { name: /기준정보/ })
  expect(screen.getByRole('link', { name: /지식 그래프/ })).toBeInTheDocument()
  fireEvent.click(title)
  expect(screen.queryByRole('link', { name: /지식 그래프/ })).toBeNull()
  expect(title).toHaveAttribute('aria-expanded', 'false')
})

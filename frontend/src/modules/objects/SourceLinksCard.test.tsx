import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { SourceLinksCard } from '@/modules/objects/SourceLinksCard'
import { AuthProvider } from '@/shared/auth/AuthContext'

const P5 = { object_id: 'm5', label: 'P5 플립', key: 'SM-P500', type_slug: 'base_model', type_label: '기본 모델', link_id: null }
const MODELS = {
  relation: 'uses_part',
  label: '적용 모델',
  incoming: true,
  single: false,
  other_types: [{ slug: 'base_model', label: '기본 모델' }],
  items: [] as unknown[],
  suggestions: [P5],
}
const KLASS = {
  relation: 'classed_as',
  label: '분류',
  incoming: false,
  single: true,
  other_types: [{ slug: 'klass', label: '부품 분류' }],
  items: [{ object_id: 'k1', label: '힌지', key: null, type_slug: 'klass', type_label: '부품 분류', link_id: 'l9' }],
  suggestions: [],
}

function serve(card: Record<string, unknown>, { admin = true }: { admin?: boolean } = {}) {
  const asked: { url: string; method: string; body: string }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    asked.push({ url, method: init?.method ?? 'GET', body: String(init?.body ?? '') })
    const me = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: admin, must_change_password: false, memberships: [] }
    let body: unknown = {}
    if (url.endsWith('/auth/refresh')) body = { access_token: 't', expires_in: 900, user: me }
    else if (url.endsWith('/parts/p1/ontology/links') && init?.method === 'POST')
      body = { type_slug: 'cc_part', rows: [{ ...MODELS, items: [{ ...P5, link_id: 'l1' }], suggestions: [] }, KLASS] }
    else if (url.endsWith('/parts/p1/ontology/links/l9') && init?.method === 'DELETE')
      body = { type_slug: 'cc_part', rows: [MODELS, { ...KLASS, items: [] }] }
    else if (url.endsWith('/parts/p1/ontology')) body = card
    else if (url.includes('/objects/base_model')) body = { items: [], total: 0, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter>
        <SourceLinksCard source="part" id="p1" canEdit={card.canEdit !== false} />
      </MemoryRouter>
    </AuthProvider>,
  )
  return asked
}

test('관계마다 칸이 서고, 걸린 것은 그 객체로 잇는다', async () => {
  serve({ type_slug: 'cc_part', rows: [MODELS, KLASS] })
  expect(await screen.findByText('적용 모델')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '힌지' })).toHaveAttribute('href', '/o/klass/k1')
  // 「하나만」 칸이 차 있으면 고르개를 안 띄운다.
  expect(screen.getAllByRole('button', { name: /고르기/ })).toHaveLength(1)
  expect(screen.getByRole('link', { name: /온톨로지에서 보기/ })).toHaveAttribute('href', '/o/cc_part/p1')
})

test('추천의 「잇기」 가 그 관계로 잇고, 서버가 준 새 칸을 그린다', async () => {
  const asked = serve({ type_slug: 'cc_part', rows: [MODELS, KLASS] })
  fireEvent.click(await screen.findByRole('button', { name: '적용 모델에 P5 플립 잇기' }))
  expect(await screen.findByRole('link', { name: 'P5 플립' })).toHaveAttribute('href', '/o/base_model/m5')
  const sent = asked.find((one) => one.method === 'POST' && one.url.endsWith('/ontology/links'))
  expect(JSON.parse(sent!.body)).toEqual({ relation: 'uses_part', object_id: 'm5' })
})

test('빼기는 그 선을 끊는다', async () => {
  const asked = serve({ type_slug: 'cc_part', rows: [MODELS, KLASS] })
  fireEvent.click(await screen.findByRole('button', { name: '분류에서 힌지 빼기' }))
  await waitFor(() => expect(asked.some((one) => one.method === 'DELETE' && one.url.endsWith('/links/l9'))).toBe(true))
  await waitFor(() => expect(screen.queryByRole('link', { name: '힌지' })).toBeNull())
})

test('고칠 수 없으면 고르기 · 빼기 · 추천이 없다', async () => {
  serve({ type_slug: 'cc_part', rows: [MODELS, KLASS], canEdit: false })
  expect(await screen.findByText('적용 모델')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /고르기|빼기|잇기/ })).toBeNull()
})

test('원 표를 비추는 타입이 없으면 시스템 관리자에게만 만드는 자리를 알린다', async () => {
  serve({ type_slug: null, rows: [] })
  expect(await screen.findByRole('link', { name: '타입 관리로' })).toHaveAttribute('href', '/admin/ontology/types')
  expect(screen.getByText(/이 부품을 가리킬 수 있습니다/)).toBeInTheDocument()
})

test('관리자가 아니면 타입이 없을 때 아무것도 그리지 않는다', async () => {
  const asked = serve({ type_slug: null, rows: [] }, { admin: false })
  await waitFor(() => expect(asked.some((one) => one.url.endsWith('/parts/p1/ontology'))).toBe(true))
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByText('기준정보')).toBeNull()
})

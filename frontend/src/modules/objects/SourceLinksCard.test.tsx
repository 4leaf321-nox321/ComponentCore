import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { SourceLinksCard } from '@/modules/objects/SourceLinksCard'
import { AuthProvider } from '@/shared/auth/AuthContext'

const PART_TYPE = { slug: 'cc_part', label: 'CompCore 부품', kind_class: 'system', system_source: 'part', properties: [] }

function serve({ types, related = [], admin = true }: { types: unknown[]; related?: unknown[]; admin?: boolean }) {
  const asked: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    asked.push(url)
    const me = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: admin, must_change_password: false, memberships: [] }
    const body = url.endsWith('/auth/refresh')
      ? { access_token: 't', expires_in: 900, user: me }
      : url.endsWith('/ontology/schema')
        ? { groups: [], types, relation_types: [], data_types: [], system_sources: [] }
        : url.endsWith('/objects/cc_part/p1')
          ? { object: { id: 'p1', label: '브래킷' }, related }
          : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter>
        <SourceLinksCard source="part" id="p1" />
      </MemoryRouter>
    </AuthProvider>,
  )
  return asked
}

test('부품을 가리키는 기준정보를 그 객체로 잇고, 잇기는 기준정보 쪽 화면으로 보낸다', async () => {
  serve({
    types: [PART_TYPE],
    related: [
      {
        relation_id: 'r1',
        relation: 'uses_part',
        label: '쓰는 제품',
        outgoing: false,
        object_id: 'o1',
        object_label: '스마트폰 A',
        object_key: 'PH-A',
        object_type_slug: 'product',
        object_type_label: '제품',
        properties: {},
        evidence_note: '',
        created_at: '2026-10-13T00:00:00Z',
      },
    ],
  })
  expect(await screen.findByRole('link', { name: '스마트폰 A' })).toHaveAttribute('href', '/o/product/o1')
  expect(screen.getByText('쓰는 제품')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /잇기/ })).toHaveAttribute('href', '/o/cc_part/p1')
})

test('원 표를 비추는 타입이 없으면 시스템 관리자에게만 만드는 자리를 알린다', async () => {
  serve({ types: [] })
  expect(await screen.findByRole('link', { name: '타입 관리로' })).toHaveAttribute('href', '/admin/ontology/types')
  expect(screen.getByText(/이 부품을 가리킬 수 있습니다/)).toBeInTheDocument()
})

test('관리자가 아니면 타입이 없을 때 아무것도 그리지 않는다', async () => {
  const asked = serve({ types: [], admin: false })
  await waitFor(() => expect(asked.some((url) => url.endsWith('/ontology/schema'))).toBe(true))
  expect(screen.queryByText('기준정보')).toBeNull()
})

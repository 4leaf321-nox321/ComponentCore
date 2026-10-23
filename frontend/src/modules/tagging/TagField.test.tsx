import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { TagField } from '@/modules/tagging/TagField'

const EMC = { object_id: 'o1', label: 'EMC', type_slug: 'cc_tag', type_label: '일반 태그' }
const CUSTOMER = { object_id: 'o2', label: '고객A', type_slug: 'customer', type_label: '고객사' }
const TYPES = [
  { slug: 'cc_tag', label: '일반 태그', icon: 'tag', mode: 'grow', can_create: true, note: '', is_default: true },
  { slug: 'customer', label: '고객사', icon: '', mode: 'pick', can_create: false, note: '', is_default: false },
]

function serve() {
  const asked: { url: string; method: string; body: string }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    asked.push({ url, method, body: String(init?.body ?? '') })
    let body: unknown = []
    if (url.endsWith('/tags/types')) body = TYPES
    else if (url.includes('/tags/types/cc_tag/objects')) body = [{ ...EMC, object_id: 'o9', label: 'EMC 시험', uses: 4 }]
    else if (url.includes('/tags/types/customer/objects')) body = []
    else if (url.endsWith('/tags/work/w1') && method === 'POST') body = [EMC, CUSTOMER, { ...EMC, object_id: 'o3', label: '진동' }]
    else if (url.endsWith('/tags/work/w1/o1') && method === 'DELETE') body = [CUSTOMER]
    else if (url.endsWith('/tags/work/w1')) body = [EMC, CUSTOMER]
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter>
      <TagField target="work" id="w1" canEdit />
    </MemoryRouter>,
  )
  return asked
}

test('칩은 그 객체로 가고, 일반 태그가 아니면 타입을 곁에 적는다', async () => {
  serve()
  expect(await screen.findByRole('link', { name: 'EMC' })).toHaveAttribute('href', '/o/cc_tag/o1')
  expect(screen.getByRole('link', { name: '고객A' })).toHaveAttribute('href', '/o/customer/o2')
  expect(screen.getByText('· 고객사')).toBeInTheDocument()
  expect(screen.queryByText('· 일반 태그')).not.toBeInTheDocument()
})

test('이름을 치면 후보가 뜨고, 같은 이름이 없으면 새로 만든다', async () => {
  const asked = serve()
  fireEvent.click(await screen.findByRole('button', { name: '태그' }))
  const input = await screen.findByRole('textbox', { name: '태그 이름' })
  fireEvent.change(input, { target: { value: '진동' } })
  // 늘리기 타입 — 많이 쓴 후보와 「새로 만들기」.
  expect(await screen.findByRole('button', { name: /EMC 시험/ })).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: /「진동」 새로 만들기/ }))
  await waitFor(() => expect(screen.getByRole('link', { name: '진동' })).toBeInTheDocument())
  const posted = asked.find((one) => one.method === 'POST')
  expect(JSON.parse(posted!.body)).toEqual({ type_slug: 'cc_tag', label: '진동' })
})

test('고르기 타입은 새로 만들지 않는다고 말한다', async () => {
  serve()
  fireEvent.click(await screen.findByRole('button', { name: '태그' }))
  const select = await screen.findByRole('combobox', { name: '태그 타입' })
  await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(2))
  fireEvent.change(select, { target: { value: 'customer' } })
  fireEvent.change(screen.getByRole('textbox', { name: '태그 이름' }), { target: { value: '고객Z' } })
  expect(await screen.findByText('고객사은(는) 있는 것에서만 고릅니다.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /새로 만들기/ })).not.toBeInTheDocument()
})

test('떼면 서버가 돌려준 목록으로 바뀐다', async () => {
  const asked = serve()
  fireEvent.click(await screen.findByRole('button', { name: 'EMC 태그 떼기' }))
  await waitFor(() => expect(screen.queryByRole('link', { name: 'EMC' })).not.toBeInTheDocument())
  expect(asked.some((one) => one.method === 'DELETE' && one.url.endsWith('/tags/work/w1/o1'))).toBe(true)
})

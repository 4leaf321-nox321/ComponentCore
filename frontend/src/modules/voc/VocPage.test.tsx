import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import VocPage from '@/modules/voc/VocPage'
import { rememberPage } from '@/shared/lib/lastPage'

const row = (seq: number, extra: Record<string, unknown> = {}) => ({
  id: `v${seq}`,
  seq,
  title: `의견 ${seq}`,
  status: 'open',
  status_label: '등록',
  page_path: null,
  created_at: '2026-10-08T01:00:00Z',
  created_by: '김',
  status_at: '2026-10-08T01:00:00Z',
  status_by: '김',
  is_mine: false,
  can_edit: false,
  event_count: 0,
  attachment_count: 0,
  ...extra,
})

type Sent = { url: string; method: string; body: unknown }

function serve(items = [row(2, { status: 'resolved', status_label: '해결', event_count: 3, attachment_count: 1, status_by: '관리자', is_mine: true }), row(1)]) {
  const sent: Sent[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const raw = init?.body
    sent.push({ url, method, body: typeof raw === 'string' ? JSON.parse(raw) : raw ?? null })
    if (url.includes('/voc/export')) return new Response(new Blob(['zip']), { status: 200, headers: { 'Content-Type': 'application/zip' } })
    const body = url.includes('/server/display')
      ? { list_page_size: 50 }
      : method === 'POST' && url.endsWith('/api/voc')
        ? { ...row(3), events: [], attachments: [] }
        : { items, total: items.length, limit: 50, offset: 0 }
    return new Response(JSON.stringify(body), { status: method === 'POST' ? 201 : 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={['/voc']}>
      <Routes>
        <Route path="/voc" element={<VocPage />} />
        <Route path="/voc/:id" element={<p>상세 화면</p>} />
      </Routes>
    </MemoryRouter>,
  )
  return sent
}

test('게시판은 번호 · 상태 · 이력 수 · 최근 처리를 보이고, 상태와 본인 것으로 거른다', async () => {
  const sent = serve()
  const resolved = (await screen.findByText('의견 2')).closest('tr')!
  expect(within(resolved).getByText('해결')).toBeInTheDocument()
  expect(within(resolved).getByText('본인')).toBeInTheDocument()
  expect(within(resolved).getByTitle('이력 3건')).toBeInTheDocument()
  expect(within(resolved).getByTitle('첨부 1개')).toBeInTheDocument()
  expect(within(resolved).getByText(/관리자/)).toBeInTheDocument()
  // 등록만 된 건의 「최근 처리」 는 비운다.
  expect(within(screen.getByText('의견 1').closest('tr')!).getByText('—')).toBeInTheDocument()

  fireEvent.click(within(screen.getByRole('group', { name: '상태 필터' })).getByRole('button', { name: '처리 중' }))
  await waitFor(() => expect(sent.some((one) => one.url.includes('status=in_progress'))).toBe(true))
  fireEvent.click(screen.getByLabelText('내가 등록한 의견만'))
  await waitFor(() => expect(sent.some((one) => one.url.includes('mine=true'))).toBe(true))
})

test('비었으면 이유를 말한다', async () => {
  serve([])
  expect(await screen.findByText('등록된 의견이 없습니다.')).toBeInTheDocument()
})

test('의견을 등록하면 보던 화면을 함께 담고 상세로 간다', async () => {
  rememberPage('/draw')
  rememberPage('/voc') // VOC 화면 자신은 적지 않는다
  const sent = serve()
  fireEvent.click(await screen.findByRole('button', { name: '의견 등록' }))
  expect(screen.getByText('/draw')).toBeInTheDocument()
  // 상태 필터에도 「등록」 칩이 있다 — 대화상자 안에서 찾는다.
  const submit = within(screen.getByRole('dialog')).getByRole('button', { name: '등록' })
  expect(submit).toBeDisabled()
  fireEvent.change(screen.getByLabelText('제목'), { target: { value: ' 도면 치수 겹침 ' } })
  fireEvent.change(screen.getByLabelText('내용'), { target: { value: '치수가 겹쳐 보입니다.' } })
  fireEvent.click(submit)
  expect(await screen.findByText('상세 화면')).toBeInTheDocument()
  const made = sent.find((one) => one.method === 'POST' && one.url.endsWith('/api/voc'))!
  expect(made.body).toEqual({ title: '도면 치수 겹침', body: '치수가 겹쳐 보입니다.', page_path: '/draw' })
})

test('고른 의견을 zip 하나로 다운로드한다', async () => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:voc')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const sent = serve()
  expect(screen.queryByRole('button', { name: /건 다운로드/ })).toBeNull()
  fireEvent.click(await screen.findByLabelText('‘의견 1’ 선택'))
  fireEvent.click(screen.getByRole('button', { name: '1건 다운로드' }))
  await waitFor(() => expect(clicked).toHaveBeenCalled())
  expect(sent.find((one) => one.url.includes('/voc/export'))!.body).toEqual({ ids: ['v1'] })
})

test('파일 크기는 1 KB 아래면 바이트로 적는다', async () => {
  const { fileSize } = await import('@/modules/voc/api')
  expect([fileSize(8), fileSize(2048), fileSize(3 * 1024 * 1024)]).toEqual(['8 B', '2 KB', '3.0 MB'])
})

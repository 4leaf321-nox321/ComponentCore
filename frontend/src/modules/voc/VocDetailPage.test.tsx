import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import VocDetailPage from '@/modules/voc/VocDetailPage'

const EVENTS = [
  { id: 'e1', at: '2026-10-08T01:00:00Z', by: '김', from_status: null, to_status: 'open', to_status_label: '등록', note: null },
  { id: 'e2', at: '2026-10-08T02:00:00Z', by: '관리자', from_status: 'open', to_status: 'accepted', to_status_label: '접수', note: '확인했습니다.' },
  { id: 'e3', at: '2026-10-08T03:00:00Z', by: '이', from_status: 'accepted', to_status: 'accepted', to_status_label: '접수', note: '저도 같습니다.' },
]

const DETAIL = {
  id: 'v1',
  seq: 12,
  title: 'STEP 업로드 실패',
  status: 'accepted',
  status_label: '접수',
  page_path: '/draw',
  created_at: '2026-10-08T01:00:00Z',
  created_by: '김',
  status_at: '2026-10-08T02:00:00Z',
  status_by: '관리자',
  is_mine: false,
  can_edit: false,
  event_count: 2,
  attachment_count: 1,
  body: '200 MB 아래인데도 거절됩니다.',
  events: EVENTS,
  attachments: [{ id: 'a1', filename: 'log.txt', content_type: 'text/plain', size: 2048, created_at: '2026-10-08T01:00:00Z', created_by: '김', url: '/api/voc/v1/attachments/a1' }],
  can_attach: false,
  allowed: ['in_progress', 'resolved', 'rejected'],
  allowed_labels: { in_progress: '처리 시작', resolved: '해결 처리', rejected: '반려' },
  note_required: ['resolved', 'rejected'],
  can_delete_events: false,
}

type Sent = { url: string; method: string; body: unknown }

function serve(detail: Record<string, unknown> = DETAIL, state?: unknown) {
  const sent: Sent[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const method = init?.method ?? 'GET'
    sent.push({ url: String(input), method, body: typeof init?.body === 'string' ? JSON.parse(init.body) : null })
    return new Response(JSON.stringify(detail), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter initialEntries={[{ pathname: '/voc/v1', state }]}>
      <Routes>
        <Route path="/voc/:id" element={<VocDetailPage />} />
        <Route path="/voc" element={<p>목록 화면</p>} />
      </Routes>
    </MemoryRouter>,
  )
  return sent
}

test('본문 · 첨부 · 이력을 보이고, 서버가 허락한 상태로만 옮긴다', async () => {
  const sent = serve()
  expect(await screen.findByText('200 MB 아래인데도 거절됩니다.')).toBeInTheDocument()
  expect(screen.getByText('#12')).toBeInTheDocument()
  expect(screen.getByText('/draw')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /log\.txt/ })).toBeInTheDocument()
  const timeline = within(screen.getByRole('list', { name: '이력' }))
  expect(timeline.getByText('확인했습니다.')).toBeInTheDocument()
  expect(timeline.getByText('댓글')).toBeInTheDocument()
  // 작성자 · 관리자가 아니면 수정 · 삭제가 없다.
  expect(screen.queryByRole('button', { name: '수정' })).toBeNull()
  expect(screen.queryByRole('button', { name: '이력 삭제' })).toBeNull()

  // 해결은 내용 없이 안 눌린다. 처리 시작은 내용 없이도 된다.
  const resolve = screen.getByRole('button', { name: '해결 처리' })
  expect(resolve).toBeDisabled()
  expect(screen.getByRole('button', { name: '처리 시작' })).toBeEnabled()
  fireEvent.change(screen.getByLabelText('댓글'), { target: { value: '업로드 상한을 고쳤습니다.' } })
  expect(resolve).toBeEnabled()
  fireEvent.click(resolve)
  await waitFor(() => expect(sent.some((one) => one.method === 'POST')).toBe(true))
  const event = sent.find((one) => one.method === 'POST')!
  expect(event.url).toMatch(/\/voc\/v1\/events$/)
  expect(event.body).toEqual({ status: 'resolved', note: '업로드 상한을 고쳤습니다.' })
})

test('댓글만 남기면 상태 없이 보낸다', async () => {
  const sent = serve({ ...DETAIL, allowed: [], allowed_labels: {}, note_required: [] })
  const comment = await screen.findByRole('button', { name: '댓글 등록' })
  expect(comment).toBeDisabled()
  fireEvent.change(screen.getByLabelText('댓글'), { target: { value: '저도 같습니다.' } })
  fireEvent.click(comment)
  await waitFor(() => expect(sent.find((one) => one.method === 'POST')?.body).toEqual({ status: null, note: '저도 같습니다.' }))
})

test('관리자는 등록 줄을 뺀 이력을 지운다', async () => {
  const sent = serve({ ...DETAIL, can_delete_events: true })
  await screen.findByText('200 MB 아래인데도 거절됩니다.')
  const removers = screen.getAllByRole('button', { name: '이력 삭제' })
  expect(removers).toHaveLength(2) // 등록 줄에는 없다
  fireEvent.click(removers[0])
  const dialog = within(await screen.findByRole('dialog'))
  expect(dialog.getByText('상태 변경: 접수')).toBeInTheDocument()
  fireEvent.click(dialog.getByRole('button', { name: '삭제' }))
  await waitFor(() => expect(sent.some((one) => one.method === 'DELETE' && one.url.endsWith('/voc/v1/events/e2'))).toBe(true))
})

test('작성자는 수정 · 삭제하고, 삭제하면 목록으로 간다', async () => {
  const sent = serve({ ...DETAIL, can_edit: true, is_mine: true })
  fireEvent.click(await screen.findByRole('button', { name: '삭제' }))
  const dialog = within(await screen.findByRole('dialog'))
  expect(dialog.getByText(/이력 3건, 첨부 1개와 함께/)).toBeInTheDocument()
  fireEvent.click(dialog.getByRole('button', { name: '삭제' }))
  expect(await screen.findByText('목록 화면')).toBeInTheDocument()
  expect(sent.some((one) => one.method === 'DELETE' && one.url.endsWith('/voc/v1'))).toBe(true)
})

test('등록하며 붙이지 못한 파일을 알린다', async () => {
  serve({ ...DETAIL, can_attach: true }, { failedFiles: ['큰파일.step'] })
  expect(await screen.findByText(/첨부하지 못한 파일이 있습니다: 큰파일\.step/)).toBeInTheDocument()
  expect(screen.getByLabelText('파일 첨부')).toBeInTheDocument()
})

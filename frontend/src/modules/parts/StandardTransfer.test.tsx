import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { StandardExportButton, StandardImportDialog } from '@/modules/parts/StandardTransfer'

const BUNDLE = {
  format: 'compcore.standard-parts',
  format_version: 1,
  exported_at: '2026-10-04T00:00:00Z',
  exported_from: 'CompCore v0.9.0',
  items: [{ name: '받침 Ø16', description: '', tags: [], folder: '', standard: { kind: 'support', part_no: 'SUP-16' }, recipe: { nodes: [] }, origin: {} }],
}

const item = (action: string, extra: Record<string, unknown> = {}) => ({ part_no: 'SUP-16', name: '받침 Ø16', kind: 'support', action, part_id: null, version: 1, problems: [], ...extra })

function serve() {
  const sent: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    sent.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null })
    let body: unknown = BUNDLE
    if (url.includes('dry_run=true')) {
      body = { dry_run: true, items: [item('create'), item('skip', { part_no: 'SUP-BAD', version: null, problems: ['바닥 중심이 원점이 아닙니다(x=30.00, y=0.00).'] })] }
    } else if (url.includes('dry_run=false')) {
      body = { dry_run: false, items: [item('create', { part_id: 'p9' }), item('skip', { part_no: 'SUP-BAD', version: null })] }
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return sent
}

test('고른 규격 부품을 묶음 파일로 내려받는다', async () => {
  const sent = serve()
  const created = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:bundle')
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(<StandardExportButton ids={['a', 'b']} />)
  fireEvent.click(screen.getByRole('button', { name: '규격 부품 내보내기 (2)' }))
  await waitFor(() => expect(clicked).toHaveBeenCalled())
  expect(sent[0].url).toMatch(/\/parts\/standard\/export$/)
  expect(sent[0].body).toEqual({ ids: ['a', 'b'] })
  expect(created).toHaveBeenCalled()
})

test('고른 것 중 규격 부품이 없으면 내보낼 수 없다', () => {
  render(<StandardExportButton ids={[]} />)
  expect(screen.getByRole('button', { name: '규격 부품 내보내기 (0)' })).toBeDisabled()
})

test('가져오기는 미리 보기를 먼저 보이고, 확인하면 반영한다', async () => {
  const sent = serve()
  const done = vi.fn()
  render(<StandardImportDialog onClose={() => {}} onDone={done} />)
  const file = new File([JSON.stringify(BUNDLE)], '규격부품.json', { type: 'application/json' })
  fireEvent.change(screen.getByLabelText('묶음 파일'), { target: { files: [file] } })

  expect(await screen.findByText(/미리 보기: 새 부품 1, 건너뜀 1/)).toBeInTheDocument()
  expect(screen.getByText('바닥 중심이 원점이 아닙니다(x=30.00, y=0.00).')).toBeInTheDocument()
  expect(sent).toHaveLength(1) // 미리 보기만 — 아직 아무것도 바꾸지 않았다
  expect(sent[0].body).toEqual(BUNDLE)

  fireEvent.click(screen.getByRole('button', { name: '가져오기 (1)' }))
  expect(await screen.findByText(/가져오기 결과: 새 부품 1, 건너뜀 1/)).toBeInTheDocument()
  expect(sent[1].url).toMatch(/dry_run=false$/)
  expect(done).toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '닫기' })).toBeInTheDocument()
})

test('JSON 이 아닌 파일은 읽지 않고 까닭을 말한다', async () => {
  const sent = serve()
  render(<StandardImportDialog onClose={() => {}} onDone={() => {}} />)
  fireEvent.change(screen.getByLabelText('묶음 파일'), { target: { files: [new File(['not json'], 'x.json')] } })
  expect(await screen.findByText(/JSON 파일을 읽을 수 없습니다/)).toBeInTheDocument()
  expect(sent).toHaveLength(0)
})

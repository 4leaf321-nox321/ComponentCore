import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { LinkDefaultsPanel } from '@/modules/objects/LinkDefaultsPanel'

const ROW = {
  label: '사용 부품',
  source_label: '기본 모델',
  target_type: 'cc_part',
  target_label: 'CompCore 부품',
  note: '',
}
const USES = { ...ROW, slug: 'uses_part', inverse_label: '적용 모델', source_type: 'base_model' }
const DESIGN = {
  ...ROW,
  slug: 'design_part',
  inverse_label: '서비스 부품',
  source_type: 'part',
  source_label: '',
  note: '출발 타입 `part` 이 아직 없습니다 — SP 기준정보(데이터 소스 › SP 코어)를 먼저 받으십시오.',
}

function serve(first: unknown[], after: unknown[]) {
  const asked: string[] = []
  let applied = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    const method = init?.method ?? 'GET'
    asked.push(method)
    let body: unknown = applied ? after : first
    if (method === 'POST') {
      applied = true
      body = { created: ['uses_part'], snapshot_id: 's1', items: after }
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return asked
}

test('만들 수 있는 것만 세어 만들고, 출발 타입이 없는 것은 까닭을 적는다', async () => {
  const asked = serve(
    [
      { ...USES, status: 'ready' },
      { ...DESIGN, status: 'missing' },
    ],
    [
      { ...USES, status: 'exists' },
      { ...DESIGN, status: 'missing' },
    ],
  )
  const changed = vi.fn()
  render(<LinkDefaultsPanel onChanged={changed} />)
  expect(await screen.findByText('「적용 모델」')).toBeInTheDocument()
  expect(screen.getByText(/SP 기준정보\(데이터 소스 › SP 코어\)를 먼저/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '1개 만들기' }))
  expect(await screen.findByText('만들었습니다: uses_part')).toBeInTheDocument()
  await waitFor(() => expect(changed).toHaveBeenCalled())
  expect(asked).toContain('POST')
  expect(await screen.findByRole('button', { name: '0개 만들기' })).toBeDisabled()
})

test('다 있으면 한 줄로 접는다', async () => {
  serve([{ ...USES, status: 'exists' }], [])
  render(<LinkDefaultsPanel onChanged={() => {}} />)
  expect(await screen.findByText(/CompCore 기본 관계\(「적용 모델」\)가 모두 있습니다/)).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

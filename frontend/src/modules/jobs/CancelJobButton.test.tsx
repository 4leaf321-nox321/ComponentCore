import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { CancelJobButton } from '@/modules/jobs/CancelJobButton'

function mockFetch() {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    calls.push(`${init?.method ?? 'GET'} ${String(input)}`)
    return new Response(JSON.stringify({ id: 'j1', status: 'running' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

test('도는 작업은 무엇이 남는지 말하고 멈추며, 멈추는 중이면 다시 누를 수 없다', async () => {
  const calls = mockFetch()
  const onCancelled = vi.fn()
  const { rerender } = render(<CancelJobButton job={{ id: 'j1', status: 'running', cancel_requested_at: null }} onCancelled={onCancelled} what="지그 생성" />)
  fireEvent.click(screen.getByRole('button', { name: '중지' }))
  expect(screen.getByText(/현재 단계를 마친 후 중지합니다/)).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: '중지' }).at(-1)!)
  await waitFor(() => expect(onCancelled).toHaveBeenCalled())
  expect(calls).toContain('POST /api/jobs/j1/cancel')

  rerender(<CancelJobButton job={{ id: 'j1', status: 'running', cancel_requested_at: '2026-10-03T00:00:00Z' }} />)
  expect(screen.getByRole('button', { name: '중지 중…' })).toBeDisabled()
  rerender(<CancelJobButton job={{ id: 'j1', status: 'done', cancel_requested_at: null }} />)
  expect(screen.queryByRole('button')).toBeNull()
})

test('대기 중이면 바로 취소한다고 말하고, DOE 는 제 길로 멈춘다', async () => {
  mockFetch()
  const cancel = vi.fn(async () => ({}))
  render(<CancelJobButton job={{ id: 'j2', status: 'queued', cancel_requested_at: null }} cancel={cancel} />)
  fireEvent.click(screen.getByRole('button', { name: '중지' }))
  expect(screen.getByText(/즉시 취소합니다/)).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: '중지' }).at(-1)!)
  await waitFor(() => expect(cancel).toHaveBeenCalled())
})

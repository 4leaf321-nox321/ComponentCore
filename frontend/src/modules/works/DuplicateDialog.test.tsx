import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { DuplicateDialog, hasConditions } from '@/modules/works/DuplicateDialog'

function mockFetch() {
  const urls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    urls.push(String(input))
    return new Response(JSON.stringify({ id: 'copy-1' }), { status: 201, headers: { 'Content-Type': 'application/json' } })
  })
  return urls
}

const CONDITIONS = { named_selections: [{ name: '바닥' }], constraints: [{ name: '고정' }], loads: [] }

test('조건이 있으면 함께 복사할지 고르고, 고른 대로 서버에 묻는다', async () => {
  const urls = mockFetch()
  const onMade = vi.fn()
  const { unmount } = render(<DuplicateDialog open workId="w1" workName="브래킷" conditions={CONDITIONS} onClose={() => {}} onMade={onMade} />)
  expect(screen.getByLabelText('이름')).toHaveValue('브래킷 사본')
  const box = screen.getByRole('checkbox', { name: /해석 조건도 복사/ })
  expect(box).toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: '복제' }))
  await waitFor(() => expect(onMade).toHaveBeenCalledWith('copy-1'))
  const asked = new URL(urls.at(-1)!, 'http://x')
  expect(asked.pathname).toBe('/api/works/w1/duplicate')
  expect(asked.searchParams.get('name')).toBe('브래킷 사본')
  expect(asked.searchParams.get('conditions')).toBe('true')
  unmount()

  // 끄면 도면만.
  render(<DuplicateDialog open workId="w1" workName="브래킷" conditions={CONDITIONS} onClose={() => {}} onMade={onMade} />)
  fireEvent.click(screen.getByRole('checkbox', { name: /해석 조건도 복사/ }))
  fireEvent.click(screen.getByRole('button', { name: '복제' }))
  await waitFor(() => expect(onMade).toHaveBeenCalledTimes(2))
  expect(urls.at(-1)).not.toContain('conditions=')
})

test('조건이 없으면 묻지 않고 도면만 복사한다고 말한다', () => {
  mockFetch()
  render(<DuplicateDialog open workId="w1" workName="받침" conditions={{ loads: [], units: {} }} onClose={() => {}} onMade={() => {}} />)
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.getByText(/해석 조건이 없습니다/)).toBeInTheDocument()
  expect(hasConditions(null)).toBe(false)
  expect(hasConditions({ analysis: { type: 'modal' } })).toBe(true)
})

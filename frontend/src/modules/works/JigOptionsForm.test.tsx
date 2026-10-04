import { fireEvent, render, screen } from '@testing-library/react'

import { JigOptionsForm } from '@/modules/works/JigOptionsForm'

test('굽힘 픽스처는 시험 규격을 고르고, 고르면 규격의 규칙이 우선한다고 말한다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
    const rows = [
      { id: 'astm-d790-16', origin: 'builtin', name: 'ASTM D790 3점 굽힘 (16:1)' },
      { id: 'u-1', origin: 'internal', name: '사내 굽힘 A' },
    ]
    return new Response(JSON.stringify(rows), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const changed = vi.fn()
  const { rerender } = render(<JigOptionsForm values={{ kind: 'bending' }} onChange={changed} />)
  expect(await screen.findByRole('option', { name: '사내 굽힘 A (사내)' })).toBeInTheDocument()
  expect(screen.queryByText(/시험 규격의 규칙이/)).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('시험 규격'), { target: { value: 'astm-d790-16' } })
  expect(changed).toHaveBeenCalledWith({ kind: 'bending', bending_preset: 'astm-d790-16' })
  rerender(<JigOptionsForm values={{ kind: 'bending', bending_preset: 'astm-d790-16' }} onChange={changed} />)
  expect(screen.getByText(/시험 규격의 규칙이 스팬/)).toBeInTheDocument()
  expect(screen.getByLabelText('하중 간격 (mm, 4점, 0 = 스팬의 1/3)')).toBeInTheDocument()
})

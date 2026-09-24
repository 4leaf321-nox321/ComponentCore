import { fireEvent, render, screen } from '@testing-library/react'

import { TagFilter } from '@/shared/components/TagFilter'

test('고른 것을 다시 누르면 풀린다 — 끄는 길이 켜는 길과 같다', () => {
  const changed = vi.fn()
  const { rerender } = render(<TagFilter tags={['브래킷', 'EMC']} value="" onChange={changed} />)

  fireEvent.click(screen.getByRole('button', { name: 'EMC' }))
  expect(changed).toHaveBeenCalledWith('EMC')

  rerender(<TagFilter tags={['브래킷', 'EMC']} value="EMC" onChange={changed} />)
  expect(screen.getByRole('button', { name: 'EMC' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'EMC' }))
  expect(changed).toHaveBeenLastCalledWith('')
})

test('누를 것이 없으면 아무것도 안 그린다', () => {
  const { container } = render(<TagFilter tags={[]} value="" onChange={() => {}} />)
  expect(container).toBeEmptyDOMElement()
})

test('목록이 아닌 것이 와도 페이지가 죽지 않는다', () => {
  // 꼬리표 하나 때문에 부품 목록을 통째로 못 보게 되면 안 된다.
  const { container } = render(
    <TagFilter tags={{} as unknown as string[]} value="" onChange={() => {}} />,
  )
  expect(container).toBeEmptyDOMElement()
})

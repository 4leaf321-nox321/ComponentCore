import { fireEvent, render, screen } from '@testing-library/react'

import { TypedTagFilter } from '@/modules/tagging/TypedTagFilter'

const TAGS = [
  { object_id: 'g1', label: 'EMC', type_slug: 'cc_tag', type_label: '일반 태그', uses: 3 },
  { object_id: 'c1', label: 'A', type_slug: 'customer', type_label: '고객사', uses: 2 },
  { object_id: 'p1', label: 'A', type_slug: 'project', type_label: '프로젝트', uses: 1 },
]

test('타입마다 묶고, 이름이 같아도 객체로 고른다', () => {
  const changed = vi.fn()
  render(<TypedTagFilter tags={TAGS} value="" onChange={changed} />)
  // 일반 태그는 타입 이름 없이, 다른 타입은 이름을 앞세워 묶는다.
  expect(screen.queryByText('일반 태그:')).not.toBeInTheDocument()
  expect(screen.getByRole('group', { name: '고객사' })).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: /^A/ })[1])
  expect(changed).toHaveBeenCalledWith('p1')
})

test('고른 것을 다시 누르면 풀고, 태그가 없으면 안 그린다', () => {
  const changed = vi.fn()
  const { rerender, container } = render(<TypedTagFilter tags={TAGS} value="g1" onChange={changed} />)
  const chosen = screen.getByRole('button', { name: /^EMC/ })
  expect(chosen).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(chosen)
  expect(changed).toHaveBeenCalledWith('')
  rerender(<TypedTagFilter tags={[]} value="" onChange={changed} />)
  expect(container).toBeEmptyDOMElement()
})

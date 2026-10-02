import { fireEvent, render, screen } from '@testing-library/react'

import { NodeForm } from '@/modules/cad/NodeForm'
import { makeNode } from '@/modules/cad/recipeSpec'
import type { RecipeNode } from '@/modules/cad/recipeSpec'

test('판 굽히기 — 굽힘을 줄마다 더하고 칸마다 고친다', () => {
  const plate: RecipeNode = { id: '판', op: 'box' }
  let node: RecipeNode = { ...makeNode('bend', [plate]), target: '판' }
  const view = () => <NodeForm node={node} nodes={[plate, node]} onChange={(next) => (node = next)} />
  const { rerender } = render(view())

  fireEvent.click(screen.getByRole('button', { name: '+ 굽힘 추가' }))
  expect(node.bends).toEqual([
    { at: 0, radius: 5, toward: 'up', until: 'angle', angle: 90 },
    { at: 30, radius: 5, toward: 'up', until: 'angle', angle: 90 },
  ])
  rerender(view())
  fireEvent.change(screen.getByLabelText('굽힘 2 시작 자리'), { target: { value: '45' } })
  expect((node.bends as { at: unknown }[])[1].at).toBe(45)
  expect((node.bends as { at: unknown }[])[0].at).toBe(0)
})

test('끝까지 감으면 각도 칸이 없다 — 남은 길이가 각도를 정한다', () => {
  const node: RecipeNode = {
    ...makeNode('bend', []),
    bends: [{ at: 0, radius: 20, toward: 'up', until: 'end', angle: 90 }],
  }
  render(<NodeForm node={node} nodes={[node]} onChange={() => {}} />)
  expect(screen.queryByLabelText('굽힘 1 각')).toBeNull()
  expect(screen.getByText(/끝까지 감습니다/)).toBeInTheDocument()
})

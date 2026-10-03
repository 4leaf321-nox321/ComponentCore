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

test('판 굽히기 — 다른 방향 날개를 더하고(상자), 날개마다 방향 · 굽힘을 고친다', () => {
  const plate: RecipeNode = { id: '판', op: 'box' }
  let node: RecipeNode = { ...makeNode('bend', [plate]), target: '판' }
  const view = () => <NodeForm node={node} nodes={[plate, node]} onChange={(next) => (node = next)} />
  const { rerender } = render(view())
  fireEvent.click(screen.getByRole('button', { name: '+ 다른 방향 날개' }))
  expect(node.also).toEqual([{ along: [0, 1, 0], bends: [{ at: 0, radius: 5, toward: 'up', until: 'angle', angle: 90 }] }])
  rerender(view())
  // 첫 날개와 둘째 날개에 같은 칸이 있다 — 둘째 것을 고친다.
  fireEvent.change(screen.getAllByLabelText('굽힘 1 시작 자리')[1], { target: { value: '30' } })
  expect((node.also as { bends: { at: unknown }[] }[])[0].bends[0].at).toBe(30)
  rerender(view())
  fireEvent.click(screen.getByLabelText('날개가 모서리에서 겹치면 따내기'))
  expect(node.corner_relief).toBe(true)
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

test('기준축을 형상에서 — 대상 입체와 「3D 에서 원통면 고르기」', () => {
  const plate: RecipeNode = { id: '판', op: 'box' }
  const node: RecipeNode = { id: '구멍축', op: 'datum_axis', target: '판', select: { what: 'faces', kind: 'cylinder' } }
  const onPickFaces = vi.fn()
  render(<NodeForm node={node} nodes={[plate, node]} onChange={() => {}} onPickFaces={onPickFaces} />)
  fireEvent.click(screen.getByRole('button', { name: '3D 에서 원통면 고르기' }))
  expect(onPickFaces).toHaveBeenCalledWith('datum')
})

test('구조 프레임 — 닫힌 틀을 알아보고, 기둥 경로를 더한다', () => {
  let node: RecipeNode = makeNode('frame', [])
  const view = () => <NodeForm node={node} nodes={[node]} onChange={(next) => (node = next)} />
  const { rerender } = render(view())
  expect(screen.getByText('경로 1 — 부재 4 개 · 닫힘')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '+ 경로 (기둥 하나부터)' }))
  expect(node.paths).toHaveLength(2)
  rerender(view())
  expect(screen.getByText('경로 2 — 부재 1 개')).toBeInTheDocument()
  // 단면 칸은 종류마다 — 알루미늄 프로파일은 계열 하나.
  expect(screen.getByLabelText('단면 계열 (20 · 30 · 40 · 45)')).toHaveValue(40)
})

test('엣지를 규칙으로 — 질의를 JSON 으로 적으면 {query} 가 된다', () => {
  let node: RecipeNode = { id: 'f', op: 'fillet', target: 'b', edges: { query: { kind: 'line' } }, radius: 1 }
  render(<NodeForm node={node} nodes={[{ id: 'b', op: 'box' }, node]} onChange={(next) => (node = next)} />)
  fireEvent.change(screen.getByLabelText('규칙 (recipe_find 질의)'), { target: { value: '{"kind":"circle","radius":5}' } })
  expect(node.edges).toEqual({ query: { kind: 'circle', radius: 5 } })
  fireEvent.change(screen.getByLabelText('규칙 (recipe_find 질의)'), { target: { value: '{"kind":' } })
  expect(screen.getByText(/JSON 이 아닙니다/)).toBeInTheDocument()
  expect(node.edges).toEqual({ query: { kind: 'circle', radius: 5 } }) // 틀린 글은 보내지 않는다
})

test('구조 프레임 — 절단 목록을 서버에서 받아 표로 보인다', async () => {
  const { cadApi } = await import('@/modules/cad/api')
  const spy = vi.spyOn(cadApi, 'cutList').mockResolvedValue({
    node: 'frame-1',
    profile: '각관 40x2',
    section_area: 304,
    items: [
      { path: 1, member: 1, length: 640, start_cut: 45, end_cut: 45, volume: 182400 },
      { path: 2, member: 1, length: 280, start_cut: 0, end_cut: 0, volume: 85120 },
    ],
    count: 2,
    total_length: 920,
    total_volume: 267520,
  })
  const node: RecipeNode = makeNode('frame', [])
  render(<NodeForm node={node} nodes={[node]} onChange={() => {}} params={{ 폭: 600 }} />)
  fireEvent.click(screen.getByRole('button', { name: '절단 목록 보기' }))
  expect(await screen.findByText(/각관 40x2 · 부재 2 개/)).toBeInTheDocument()
  expect(screen.getAllByText('45°')).toHaveLength(2)
  expect(screen.getAllByText('직각')).toHaveLength(2)
  expect(spy).toHaveBeenCalledWith({ params: { 폭: 600 }, nodes: [node] }, node.id)
})

test('곡면 — 점 격자는 JSON 으로 적고, 읽히면 바로 반영하고 아니면 붉힌다', () => {
  let node: RecipeNode = makeNode('surface', [])
  const view = () => <NodeForm node={node} nodes={[node]} onChange={(next) => (node = next)} />
  const { rerender } = render(view())
  const field = screen.getByLabelText(/점 격자/)
  fireEvent.change(field, { target: { value: '[[[0,0,0],[10,0,0]],[[0,10,0],[10,10,2]]]' } })
  expect(node.grid).toEqual([
    [
      [0, 0, 0],
      [10, 0, 0],
    ],
    [
      [0, 10, 0],
      [10, 10, 2],
    ],
  ])
  rerender(view())
  fireEvent.change(screen.getByLabelText(/점 격자/), { target: { value: '[[[0,0' } })
  expect(screen.getByLabelText(/점 격자/).className).toContain('border-destructive')
})

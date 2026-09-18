import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Recipe } from '@/modules/cad/api'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'

const BOX: Recipe = {
  nodes: [
    { id: 's', op: 'sketch', label: '바닥', shapes: [{ type: 'rect', width: 40, height: 30, at: [0, 0], rotation: 0, mode: 'add' }] },
    { id: 'b', op: 'extrude', sketch: 's', distance: 10, direction: 'normal' },
  ],
}

beforeEach(() => {
  // check 는 통과, mesh 는 안 준다(WebGL 이 없는 시험 환경에서 뷰어를 안 띄우려고).
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/cad/recipe/check')) return new Response(JSON.stringify({ ok: true, problems: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    return new Response(JSON.stringify({ error: { code: 'AJG-TEST-0001', message: '없음' } }), { status: 500, headers: { 'Content-Type': 'application/json' } })
  })
})

test('피처 트리를 그리고, 칸을 고치면 레시피가 바뀐다', async () => {
  const onChange = vi.fn()
  render(<RecipeEditor value={BOX} onChange={onChange} />)
  // 트리에 두 피처 — 이름이 있으면 이름, 없으면 연산 이름. 누르면 모달이 뜬다.
  expect(screen.getByText('바닥')).toBeInTheDocument()
  // 툴바에도 「돌출」 단추가 있으니 트리 항목은 id 로 찾는다.
  fireEvent.click(screen.getByText('b').closest('button')!)
  const distance = screen.getByLabelText('거리 (mm)') as HTMLInputElement
  expect(distance.value).toBe('10')
  fireEvent.change(distance, { target: { value: '25' } })
  await waitFor(() => expect(onChange).toHaveBeenCalled())
  const next = onChange.mock.calls.at(-1)![0] as Recipe
  expect(next.nodes[1].distance).toBe(25)
  expect(next.nodes[0]).toEqual(BOX.nodes[0])
})

test('스케치 피처를 고르면 캔버스가 뜬다', () => {
  render(<RecipeEditor value={BOX} onChange={() => {}} />)
  fireEvent.click(screen.getByText('바닥'))
  expect(screen.getByRole('button', { name: '선택 · 이동' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '+ 원' })).toBeInTheDocument()
})

test('id 를 바꾸면 그것을 가리키는 뒤 피처도 따라간다', async () => {
  const onChange = vi.fn()
  render(<RecipeEditor value={BOX} onChange={onChange} />)
  fireEvent.click(screen.getByText('바닥'))
  const id = screen.getByLabelText('id') as HTMLInputElement
  fireEvent.change(id, { target: { value: 'base' } })
  await waitFor(() => expect(onChange).toHaveBeenCalled())
  const next = onChange.mock.calls.at(-1)![0] as Recipe
  expect(next.nodes[0].id).toBe('base')
  expect(next.nodes[1].sketch).toBe('base')
})

test('리본 — 탭이 종류를 가르고, 「파일」 탭 단추가 호출부의 일을 부른다', async () => {
  const onChange = vi.fn()
  const save = vi.fn()
  const downloadStep = vi.fn()
  render(<RecipeEditor value={BOX} onChange={onChange} file={{ save: { label: '내 작업으로', run: save }, downloadStep }} />)
  // 피처가 있으면 스케치 탭에서 시작. 입체 탭으로 가면 돌출 단추가 보인다(radix 탭은 mouseDown 에 바뀐다).
  expect(screen.getByRole('button', { name: /^스케치$/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^돌출/ })).toBeNull()
  fireEvent.mouseDown(screen.getByRole('tab', { name: '입체' }))
  fireEvent.click(screen.getByRole('button', { name: /^돌출/ }))
  await waitFor(() => expect(onChange).toHaveBeenCalled())
  expect((onChange.mock.calls.at(-1)![0] as Recipe).nodes).toHaveLength(3)

  fireEvent.mouseDown(screen.getByRole('tab', { name: '파일' }))
  fireEvent.click(screen.getByRole('button', { name: /내 작업으로/ }))
  expect(save).toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: /STEP/ }))
  expect(downloadStep).toHaveBeenCalled()
})

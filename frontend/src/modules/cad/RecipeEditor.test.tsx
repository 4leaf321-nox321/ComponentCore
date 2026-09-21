import { createEvent, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

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
    return new Response(JSON.stringify({ error: { code: 'CCR-TEST-0001', message: '없음' } }), { status: 500, headers: { 'Content-Type': 'application/json' } })
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
  const download = vi.fn()
  render(<RecipeEditor value={BOX} onChange={onChange} file={{ save: { label: '내 작업으로', run: save }, download }} />)
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
  expect(download).toHaveBeenCalledWith('step')
  fireEvent.click(screen.getByRole('button', { name: /DXF/ }))
  expect(download).toHaveBeenCalledWith('dxf')
})

test('실행 취소 · 다시 실행 — 호출부가 value 를 되돌려 주면 한 걸음씩 오간다', async () => {
  function Host() {
    const [recipe, setRecipe] = useState<Recipe>(BOX)
    return <RecipeEditor value={recipe} onChange={setRecipe} />
  }
  render(<Host />)
  fireEvent.mouseDown(screen.getByRole('tab', { name: '입체' }))
  fireEvent.click(screen.getByRole('button', { name: /^블록/ }))
  await waitFor(() => expect(screen.getAllByText('box-1').length).toBeGreaterThan(0))
  // 새 피처의 모달이 열려 있다 — 닫아야 뒤의 단추가 접근 가능하다.
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  const undo = screen.getByRole('button', { name: '실행 취소' })
  await waitFor(() => expect(undo).toBeEnabled())
  fireEvent.click(undo)
  await waitFor(() => expect(screen.queryAllByText('box-1')).toHaveLength(0))
  fireEvent.click(screen.getByRole('button', { name: '다시 실행' }))
  await waitFor(() => expect(screen.getAllByText('box-1').length).toBeGreaterThan(0))
})

const THREE: Recipe = {
  nodes: [
    { id: 'plate', op: 'box', length: 40, width: 30, height: 10, at: [0, 0, 0] },
    { id: 's', op: 'sketch', label: '바닥', shapes: [{ type: 'rect', width: 40, height: 30, at: [0, 0], rotation: 0, mode: 'add' }] },
    { id: 'e', op: 'extrude', sketch: 's', distance: 10, direction: 'normal' },
  ],
}

/** happy-dom 은 크기를 0 으로 준다 — 칸의 위/아래 절반을 가르려면 실제 값이 필요하다. */
function withBox(element: Element, top: number) {
  element.getBoundingClientRect = () => ({ top, height: 20, bottom: top + 20, left: 0, right: 100, width: 100, x: 0, y: top, toJSON: () => ({}) }) as DOMRect
}
function dragData() {
  return { effectAllowed: '', dropEffect: '', setData: vi.fn(), getData: () => '' }
}

/** 이 시험 환경의 드래그 이벤트에는 마우스 좌표가 없다 — 칸의 위/아래를 가르려면 직접 얹는다. */
function dragOverAt(row: Element, clientY: number) {
  const event = createEvent.dragOver(row, { dataTransfer: dragData() })
  Object.defineProperty(event, 'clientY', { value: clientY })
  fireEvent(row, event)
}

test('목록의 고치기 · 지우기는 손을 올렸을 때 쓰고, 지우면 그 피처가 빠진다', () => {
  const onChange = vi.fn()
  render(<RecipeEditor value={THREE} onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: 'plate 고치기' }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })

  fireEvent.click(screen.getByRole('button', { name: 'plate 지우기' }))
  const next = onChange.mock.calls.at(-1)![0] as Recipe
  expect(next.nodes.map((n) => n.id)).toEqual(['s', 'e'])
})

test('끌어서 순서를 바꾸되, 선후관계가 있으면 놓지 못한다', () => {
  const onChange = vi.fn()
  const { container } = render(<RecipeEditor value={THREE} onChange={onChange} />)
  const rows = container.querySelectorAll('ol > li')
  rows.forEach((row, i) => withBox(row, i * 20))

  // 돌출(e)을 스케치(s) 앞으로 → 막힌다. onChange 가 없고 이유가 뜬다.
  fireEvent.dragStart(rows[2], { dataTransfer: dragData() })
  dragOverAt(rows[1], 21) // 칸의 위 절반 = 이 앞에 놓기
  fireEvent.drop(rows[1], { dataTransfer: dragData() })
  expect(onChange).not.toHaveBeenCalled()
  expect(screen.getByText(/먼저 올 수 없습니다/)).toBeInTheDocument()
  fireEvent.dragEnd(rows[2])

  // 상자(plate)는 아무도 안 쓰니 스케치 뒤로 갈 수 있다.
  fireEvent.dragStart(rows[0], { dataTransfer: dragData() })
  dragOverAt(rows[2], 41)
  fireEvent.drop(rows[2], { dataTransfer: dragData() })
  const next = onChange.mock.calls.at(-1)![0] as Recipe
  expect(next.nodes.map((n) => n.id)).toEqual(['s', 'plate', 'e'])
})

test('STEP 열기는 「파일」 탭에 있고, 전체 화면은 어느 탭에서나 오른쪽 위에 있다', () => {
  const importStep = vi.fn()
  const { container } = render(<RecipeEditor value={BOX} onChange={() => {}} file={{ importStep: { label: 'STEP 열기', run: importStep } }} />)
  // 전체 화면은 탭 밖 — 지금 탭(스케치)에서도 보인다.
  expect(screen.getByRole('button', { name: /전체 화면/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'STEP 열기' })).toBeNull()

  fireEvent.mouseDown(screen.getByRole('tab', { name: '파일' }))
  fireEvent.click(screen.getByRole('button', { name: 'STEP 열기' }))
  // 감춰 둔 파일 칸이 열리고, 고른 파일이 호출부로 간다.
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  const picked = new File(['ISO-10303-21;'], 'part.step')
  Object.defineProperty(input, 'files', { value: [picked] })
  fireEvent.change(input)
  expect(importStep).toHaveBeenCalledWith(picked)
  expect(screen.getByRole('button', { name: /전체 화면/ })).toBeInTheDocument()
})

test('칸에서 만든 변수가 사라지지 않는다 — 한 동작이 레시피를 두 번 고칠 때', async () => {
  function Host() {
    const [recipe, setRecipe] = useState<Recipe>(BOX)
    return (
      <>
        <RecipeEditor value={recipe} onChange={setRecipe} />
        <pre data-testid="recipe">{JSON.stringify(recipe)}</pre>
      </>
    )
  }
  render(<Host />)
  // 돌출 피처를 열어 「거리」 칸을 변수로 바꾼다.
  fireEvent.click(screen.getByRole('button', { name: 'b 고치기' }))
  fireEvent.click(await screen.findByRole('button', { name: '거리 (mm) 변수로' }))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '두께' } })
  fireEvent.click(screen.getByRole('button', { name: '만들기' }))

  const recipe = JSON.parse(screen.getByTestId('recipe').textContent!) as Recipe
  // 변수가 남아 있고(예전에는 두 번째 갱신이 덮어 지웠다), 칸이 그것을 가리킨다.
  expect(recipe.params).toEqual({ 두께: 10 })
  expect(recipe.nodes[1].distance).toBe('=두께')
})

test('스케치 도형 칸에서 만든 변수도 남는다', async () => {
  function Host() {
    const [recipe, setRecipe] = useState<Recipe>(BOX)
    return (
      <>
        <RecipeEditor value={recipe} onChange={setRecipe} />
        <pre data-testid="recipe">{JSON.stringify(recipe)}</pre>
      </>
    )
  }
  render(<Host />)
  fireEvent.click(screen.getByRole('button', { name: 's 고치기' })) // 스케치 피처(id: s)
  // 스케치 모달의 사각형 「너비」 칸.
  fireEvent.click(await screen.findByRole('button', { name: '너비 변수로' }))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '판_폭' } })
  fireEvent.click(screen.getByRole('button', { name: '만들기' }))

  const recipe = JSON.parse(screen.getByTestId('recipe').textContent!) as Recipe
  expect(recipe.params).toEqual({ 판_폭: 40 })
  expect((recipe.nodes[0].shapes as { width: unknown }[])[0].width).toBe('=판_폭')
})

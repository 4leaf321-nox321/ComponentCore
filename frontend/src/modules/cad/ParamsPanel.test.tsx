import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { ParamsPanel } from '@/modules/cad/ParamsPanel'

const RECIPE: Recipe = {
  params: { 판_길이: 80 },
  nodes: [
    { id: 'p', op: 'box', length: '=판_길이', width: 50, height: 10 },
    { id: 'h', op: 'hole', target: 'p', at: [['=판_길이 - 15', 0]], diameter: 6 },
  ],
}

function Host() {
  const [recipe, setRecipe] = useState<Recipe>(RECIPE)
  return (
    <>
      <ParamsPanel value={recipe} onChange={setRecipe} />
      <pre data-testid="json">{JSON.stringify(recipe)}</pre>
    </>
  )
}

test('변수를 고치면 레시피의 params 가 바뀐다 — 그것을 쓰는 칸은 서버가 푼다', () => {
  render(<Host />)
  fireEvent.change(screen.getByLabelText('변수 판_길이'), { target: { value: '120' } })
  expect(JSON.parse(screen.getByTestId('json').textContent!).params).toEqual({ 판_길이: 120 })
})

test('변수 이름을 바꾸면 그것을 쓰던 식도 따라 바뀐다 — 안 그러면 레시피가 깨진다', () => {
  render(<Host />)
  fireEvent.blur(screen.getByLabelText('변수 이름 판_길이'), { target: { value: '길이' } })
  const recipe = JSON.parse(screen.getByTestId('json').textContent!) as Recipe
  expect(recipe.params).toEqual({ 길이: 80 })
  expect(recipe.nodes[0].length).toBe('=길이')
  expect((recipe.nodes[1].at as string[][])[0][0]).toBe('=길이 - 15')
})

test('변수를 만들고 지운다', () => {
  render(<Host />)
  fireEvent.click(screen.getByLabelText('변수 만들기'))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '두께' } })
  fireEvent.submit(screen.getByLabelText('새 변수 이름').closest('form')!)
  expect(JSON.parse(screen.getByTestId('json').textContent!).params).toEqual({ 판_길이: 80, 두께: 10 })
  fireEvent.click(screen.getByLabelText('변수 두께 지우기'))
  expect(JSON.parse(screen.getByTestId('json').textContent!).params).toEqual({ 판_길이: 80 })
})

test('변수가 어느 칸에서 쓰이는지 세어 보여 준다 — 안 쓰이면 그렇게 말한다', () => {
  render(<Host />)
  // 판_길이 는 box.length 와 hole.at 두 칸에서 쓴다.
  expect(screen.getByTitle('2 칸에서 씁니다')).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('변수 만들기'))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '안쓰는것' } })
  fireEvent.submit(screen.getByLabelText('새 변수 이름').closest('form')!)
  expect(screen.getByText('안 쓰임')).toBeInTheDocument()
})

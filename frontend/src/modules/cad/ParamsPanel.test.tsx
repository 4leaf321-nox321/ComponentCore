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
  fireEvent.click(screen.getByLabelText('변수 생성'))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '두께' } })
  fireEvent.submit(screen.getByLabelText('새 변수 이름').closest('form')!)
  expect(JSON.parse(screen.getByTestId('json').textContent!).params).toEqual({ 판_길이: 80, 두께: 10 })
  fireEvent.click(screen.getByLabelText('변수 두께 삭제'))
  expect(JSON.parse(screen.getByTestId('json').textContent!).params).toEqual({ 판_길이: 80 })
})

test('변수가 어느 칸에서 쓰이는지 세어 보여 준다 — 안 쓰이면 그렇게 말한다', () => {
  render(<Host />)
  // 판_길이 는 box.length 와 hole.at 두 칸에서 쓴다.
  expect(screen.getByTitle('2개 입력란에서 사용합니다.')).toBeInTheDocument()
  expect(screen.getByText('입력란 2')).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('변수 생성'))
  fireEvent.change(screen.getByLabelText('새 변수 이름'), { target: { value: '안쓰는것' } })
  fireEvent.submit(screen.getByLabelText('새 변수 이름').closest('form')!)
  expect(screen.getByText('미사용')).toBeInTheDocument()
})

/** 규격 시편처럼 — 식으로 정의된 변수, 다른 변수의 식에서만 쓰는 변수, 해석 조건에서만 쓰는 변수. */
const SPECIMEN: Recipe = {
  params: { 두께: 3.2, 간격비: 16, 지지_간격: '=간격비 * 두께', 마찰계수: 0.1, 길이: 127 },
  nodes: [
    { id: '시편', op: 'box', length: '=판길이', width: 12.7, height: '=두께' },
    { id: '롤러_1', op: 'cylinder', radius: 5, height: 20, at: ['=-지지_간격 / 2', 0, -5] },
  ],
}
const CONDITIONS = { contacts: [{ name: '시편-롤러', type: 'frictional', friction: '=마찰계수' }] }

function SpecimenHost() {
  const [recipe, setRecipe] = useState<Recipe>(SPECIMEN)
  return (
    <>
      <ParamsPanel value={recipe} onChange={setRecipe} conditions={CONDITIONS} />
      <pre data-testid="json">{JSON.stringify(recipe)}</pre>
    </>
  )
}

test('다른 변수의 식이나 해석 조건에서만 쓰는 변수는 미사용이 아니다 — 지우지 못한다', () => {
  render(<SpecimenHost />)
  // 간격비 는 지지_간격 의 식에서, 마찰계수 는 조건에서 쓴다.
  expect(screen.getByTitle('변수 지지_간격의 식에서 사용합니다.')).toHaveTextContent('변수')
  expect(screen.getByTitle(/해석 조건 1곳에서 사용합니다/)).toHaveTextContent('조건')
  expect(screen.getByLabelText('변수 간격비 삭제')).toBeDisabled()
  expect(screen.getByLabelText('변수 마찰계수 삭제')).toBeDisabled()
  // 조건이 쓰는 변수는 이름도 못 바꾼다 — 조건은 이 화면이 고치지 않는다.
  expect(screen.getByLabelText('변수 이름 마찰계수')).toHaveAttribute('readonly')
  // 한글 이름의 경계 — 「길이」 는 「=판길이」 안에서 걸리지 않는다.
  expect(screen.getByTitle(/어디에서도 사용하지 않습니다/)).toHaveTextContent('미사용')
})

test('식으로 정의된 변수는 식 그대로 보이고, 이름을 바꾸면 다른 변수의 식도 따라간다', () => {
  render(<SpecimenHost />)
  expect(screen.getByLabelText('변수 지지_간격')).toHaveValue('=간격비 * 두께')
  fireEvent.blur(screen.getByLabelText('변수 이름 두께'), { target: { value: '판_두께' } })
  let recipe = JSON.parse(screen.getByTestId('json').textContent!) as Recipe
  expect(recipe.params?.지지_간격).toBe('=간격비 * 판_두께')
  expect(recipe.nodes[0].height).toBe('=판_두께')
  // 숫자를 넣으면 고정 값이 된다.
  fireEvent.change(screen.getByLabelText('변수 지지_간격'), { target: { value: '60' } })
  recipe = JSON.parse(screen.getByTestId('json').textContent!) as Recipe
  expect(recipe.params?.지지_간격).toBe(60)
})

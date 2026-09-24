import { appliedTo, assignBody, materialsOn } from '@/modules/conditions/api'

const 판 = ['바닥판', '기둥', '상판']

test('옛 값(문자열 하나)도 목록으로 읽고, 칸이 없으면 서버처럼 「전체」 다', () => {
  expect(appliedTo({ apply_to: '기둥' })).toEqual(['기둥'])
  expect(appliedTo({ apply_to: '' })).toEqual([])
  expect(appliedTo({})).toEqual(['전체'])
  expect(appliedTo({ apply_to: ['기둥', '기둥', '상판'] })).toEqual(['기둥', '상판'])
})

test('「전체」 에 붙은 물성이 있으면, 한 파트만 바꿀 때 **나머지는 그대로** 남는다', () => {
  // 옛 화면이 만든 모양 — 조립인데 물성 하나가 「전체」 에 붙어 있다.
  const before = [{ apply_to: '전체' }, { apply_to: [] as string[] }]
  const after = assignBody(before, 판, '기둥', 1)
  expect(after.map(appliedTo)).toEqual([['바닥판', '상판'], ['기둥']])
})

test('지정 해제는 그 파트만 뺀다', () => {
  const after = assignBody([{ apply_to: ['바닥판', '기둥'] }], 판, '기둥', null)
  expect(after.map(appliedTo)).toEqual([['바닥판']])
})

test('단품은 파트가 「전체」 하나다 — 풀어 쓸 것이 없다', () => {
  const after = assignBody([{ apply_to: ['전체'] }, { apply_to: [] as string[] }], ['전체'], '전체', 1)
  expect(after.map(appliedTo)).toEqual([[], ['전체']])
})

test('한 파트를 둘이 가리키면 둘 다 알려 준다 — 저장이 막히는 모양이다', () => {
  expect(materialsOn([{ apply_to: ['기둥'] }, { apply_to: '전체' }], '기둥')).toEqual([0, 1])
  expect(materialsOn([{ apply_to: ['기둥'] }], '상판')).toEqual([])
})

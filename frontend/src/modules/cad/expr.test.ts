import { evalNumber, isExpression, resolvedText } from '@/modules/cad/expr'

const PARAMS = { 판_길이: 80, 두께: 10 }

test('서버와 같은 식을 같은 값으로 푼다', () => {
  expect(evalNumber('=판_길이', PARAMS)).toBe(80)
  expect(evalNumber('=판_길이 - 15', PARAMS)).toBe(65)
  expect(evalNumber('=판_길이 / 2 + 두께', PARAMS)).toBe(50)
  expect(evalNumber('=(판_길이 + 두께) * 2', PARAMS)).toBe(180)
  expect(evalNumber('=2 ** 3', PARAMS)).toBe(8)
  expect(evalNumber('=min(판_길이, 두께) * 3', PARAMS)).toBe(30)
  expect(evalNumber('=sqrt(16)', PARAMS)).toBe(4)
  expect(evalNumber('=-두께', PARAMS)).toBe(-10)
  expect(evalNumber('=cos(0) * 5', PARAMS)).toBe(5)
})

test('숫자는 그대로, 식이 아니면 그대로 읽는다', () => {
  expect(evalNumber(40)).toBe(40)
  expect(evalNumber('40')).toBe(40)
  expect(isExpression('=두께')).toBe(true)
  expect(isExpression('두께')).toBe(false)
})

test('못 푸는 식은 NaN — 틀린 값을 그럴듯하게 그리지 않는다', () => {
  expect(Number.isNaN(evalNumber('=없는이름', PARAMS))).toBe(true)
  expect(Number.isNaN(evalNumber('=(1 + 2', PARAMS))).toBe(true)
  expect(Number.isNaN(evalNumber('=1 + ', PARAMS))).toBe(true)
  expect(resolvedText('=없는이름', PARAMS)).toBe('')
  expect(resolvedText('=판_길이 / 2', PARAMS)).toBe('40')
})

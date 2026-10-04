import type { Recipe } from '@/modules/cad/api'
import { elementOf, elementsOf, movable, moveElement, withProduct } from '@/modules/works/jigEdit'

/** 생성기가 내는 모양 그대로(줄임) — 판 · 받침 · 클램프(기둥 + 회전한 팔 + 패드)를 묶음 「지그」 로. */
const JIG = {
  version: 1,
  params: { 받침_높이: 12 },
  nodes: [
    { id: '바닥판_몸통', op: 'box', length: 100, width: 80, height: 10, at: [0, 0, 0] },
    { id: '바닥판', op: 'hole', target: '바닥판_몸통', diameter: 6, at: [[-40, -30], [40, 30]] },
    { id: '받침_1', op: 'cylinder', radius: 5, height: '=받침_높이', at: [-30, -20, 0] },
    { id: '클램프_1_기둥', op: 'box', length: 12, width: 12, height: 30, at: [50, 0, 0] },
    { id: '클램프_1_팔_자리', op: 'box', length: 30, width: 10, height: 5, at: [0, 0, 0] },
    { id: '클램프_1_팔', op: 'transform', target: '클램프_1_팔_자리', rotate: [0, 0, 180], translate: [50, 0, '=받침_높이 + 20'] },
    { id: '클램프_1_패드', op: 'cylinder', radius: 4, height: 2, at: ['=판_길이/2 - 30', 0, '=받침_높이 + 18'] },
    { id: '클램프_1', op: 'union', targets: ['클램프_1_기둥', '클램프_1_팔', '클램프_1_패드'] },
    { id: '지그', op: 'group', targets: ['바닥판', '받침_1', '클램프_1'] },
  ],
  result: '지그',
} as unknown as Recipe

const PRODUCT = { id: '제품', op: 'component', source: 'work:w1@1', translate: [0, 0, '=받침_높이 + 0'] }

test('제품은 결과 묶음의 자식으로 덧붙고, 원래 레시피는 그대로다', () => {
  const composed = withProduct(JIG, PRODUCT)
  expect(elementsOf(composed)).toEqual(['바닥판', '받침_1', '클램프_1', '제품'])
  const ids = (composed.nodes as { id: string }[]).map((one) => one.id)
  expect(ids.indexOf('제품')).toBe(ids.indexOf('지그') - 1)
  expect(elementsOf(JIG)).toEqual(['바닥판', '받침_1', '클램프_1'])
  // 결과가 묶음이 아니면 둘을 새 묶음으로.
  const single = withProduct({ nodes: [{ id: 'b', op: 'box', length: 1, width: 1, height: 1 }] } as unknown as Recipe, PRODUCT)
  expect(single.result).toBe('간섭_검사')
  expect(elementsOf(single)).toEqual(['b', '제품'])
})

test('피처는 그것을 이루는 요소로 거슬러 올라간다', () => {
  expect(elementOf(JIG, '클램프_1_팔_자리')).toBe('클램프_1')
  expect(elementOf(JIG, '바닥판_몸통')).toBe('바닥판')
  expect(elementOf(JIG, '받침_1')).toBe('받침_1')
  expect(elementOf(JIG, '없음')).toBeNull()
  expect(movable('받침_1', '제품')).toBe(true)
  expect(movable('바닥판', '제품') || movable('제품', '제품') || movable(null)).toBe(false)
})

test('요소를 XY 로 옮기면 그 피처들의 자리가 함께 간다 — 높이 · 회전 노드 아래의 도형은 그대로', () => {
  const moved = moveElement(JIG, '클램프_1', 5, -2)
  const byId = Object.fromEntries((moved.nodes as { id: string }[]).map((one) => [one.id, one])) as Record<string, Record<string, unknown>>
  expect(byId['클램프_1_기둥'].at).toEqual([55, -2, 0])
  expect(byId['클램프_1_팔'].translate).toEqual([55, -2, '=받침_높이 + 20'])
  expect(byId['클램프_1_팔_자리'].at).toEqual([0, 0, 0]) // 회전 · 이동 노드가 옮긴다 — 두 번 가지 않는다
  expect(byId['클램프_1_패드'].at).toEqual(['=(판_길이/2 - 30) + 5', -2, '=받침_높이 + 18'])
  expect(byId['받침_1'].at).toEqual([-30, -20, 0])
  const support = moveElement(JIG, '받침_1', 0.1234, 0)
  expect((support.nodes as { id: string; at?: unknown }[]).find((one) => one.id === '받침_1')!.at).toEqual([-29.877, -20, 0])
})

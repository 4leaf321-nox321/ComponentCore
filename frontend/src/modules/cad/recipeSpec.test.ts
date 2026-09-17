/**
 * 편집기의 노드 목록이 서버 스키마와 어긋나지 않는지 — 서버가 연산을 더하면 여기서 드러난다.
 *
 * openapi.json 이 아니라 서버가 export 한 JSON Schema 를 읽고 싶지만 시험은 서버 없이 돈다.
 * 대신 백엔드 `core/recipe/schema.py` 의 op 리터럴을 파일에서 긁는다.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { OP_BY_NAME, OP_SPECS, makeNode, nodeKind, referencesOf } from '@/modules/cad/recipeSpec'

const SCHEMA = readFileSync(resolve(__dirname, '../../../../backend/app/core/recipe/schema.py'), 'utf-8')

test('서버의 모든 연산이 편집기에 있다', () => {
  const ops = [...SCHEMA.matchAll(/op: Literal\["([a-z_]+)"\]/g)].map((m) => m[1])
  expect(ops.length).toBeGreaterThan(10)
  for (const op of ops) expect(OP_BY_NAME[op], op).toBeDefined()
  for (const spec of OP_SPECS) expect(ops, spec.op).toContain(spec.op)
})

test('새 노드의 기본값은 스키마의 칸만 쓴다', () => {
  for (const spec of OP_SPECS) {
    const node = makeNode(spec.op, [])
    expect(node.id).toBe(`${spec.op}-1`)
    for (const key of Object.keys(spec.defaults)) {
      // 칸 이름이 서버 클래스에 있어야 한다 — 없는 칸은 extra="forbid" 로 거절된다.
      expect(SCHEMA, `${spec.op}.${key}`).toMatch(new RegExp(`\\b${key}:`))
    }
  }
})

test('참조와 종류 판정', () => {
  const sketch = makeNode('sketch', [])
  const extrude = { ...makeNode('extrude', [sketch]), sketch: sketch.id }
  const pattern = { ...makeNode('pattern', [sketch, extrude]), source: extrude.id }
  expect(referencesOf(extrude)).toEqual([sketch.id])
  expect(nodeKind(sketch, [sketch])).toBe('sketch')
  expect(nodeKind(pattern, [sketch, extrude, pattern])).toBe('solid')
})

/**
 * 생성 타입(`@/shared/api/schema`)을 **화면 코드가 가져오지 않는다.**
 *
 * `schema.d.ts` 는 커밋하지 않는 생성물이다(`npm run api:types`). 개발 PC 와 CI 의 프론트 잡은 그것을
 * 먼저 만들어 통과하지만, 릴리스 번들 빌드(`deploy/build_bundle.sh`)에는 없어 거기서만 깨진다 —
 * v0.4.50(2026-10-09, `objects/api.ts`)과 v0.27.0(2026-11-17, MatNexus 에서 옮긴 `notices/api.ts`)
 * 두 번 태그 직전에 떨어졌다. 서버 스키마와 같은 모양을 손으로 적는다.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return sources(path)
    return /\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.d.ts') ? [path] : []
  })
}

test('생성 타입을 가져오는 화면 코드가 없다 — 번들 빌드에는 그 파일이 없다', () => {
  // 줄 머리의 import · export 문만 — 설명 주석 속의 예(`types.ts`)는 코드가 아니다.
  const importing = sources('src').filter((path) => /^\s*(import|export)\b[^\n]*from\s+['"]@\/shared\/api\/schema['"]/m.test(readFileSync(path, 'utf8')))
  expect(importing).toEqual([])
})

/**
 * 레시피를 파일로 받는다 — STEP(다른 CAD) · STL(3D 프린터) · DXF/SVG(2D 도면).
 *
 * 브라우저에는 「이 blob 을 내려받아라」 가 따로 없어서 임시 <a> 를 만들어 누른다. URL 은 잠시
 * 뒤 되돌린다 — 바로 지우면 느린 브라우저가 못 받는다.
 */

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'

/**
 * `flat` 은 **전개도 DXF** — 굽힌 판을 펼친 모양(외곽 · 굽힘선 · 방향과 각). `mid` 는
 * **중간면 STEP** — 얇은 판의 두께 가운데 면(셸 요소 해석용, 솔리드가 아니다).
 */
export type DownloadFormat = 'step' | 'stl' | 'dxf' | 'svg' | 'flat' | 'mid'

const SPECIAL: Partial<Record<DownloadFormat, { fetch: (recipe: Recipe) => Promise<Blob>; suffix: string }>> = {
  flat: { fetch: (recipe) => cadApi.flat(recipe, 'dxf'), suffix: '-전개도.dxf' },
  mid: { fetch: (recipe) => cadApi.midsurface(recipe), suffix: '-중간면.step' },
}

export async function saveRecipeAs(recipe: Recipe, format: DownloadFormat, name = 'model'): Promise<void> {
  const special = SPECIAL[format]
  const blob = special ? await special.fetch(recipe) : await cadApi[format as 'step' | 'stl' | 'dxf' | 'svg'](recipe)
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = special ? `${name}${special.suffix}` : `${name}.${format}`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(href), 10_000)
}

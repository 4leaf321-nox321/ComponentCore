/**
 * 레시피를 파일로 받는다 — STEP(다른 CAD) · STL(3D 프린터) · DXF/SVG(2D 도면).
 *
 * 브라우저에는 「이 blob 을 내려받아라」 가 따로 없어서 임시 <a> 를 만들어 누른다. URL 은 잠시
 * 뒤 되돌린다 — 바로 지우면 느린 브라우저가 못 받는다.
 */

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'

export type DownloadFormat = 'step' | 'stl' | 'dxf' | 'svg'

export async function saveRecipeAs(recipe: Recipe, format: DownloadFormat, name = 'model'): Promise<void> {
  const blob = await cadApi[format](recipe)
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = `${name}.${format}`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(href), 10_000)
}

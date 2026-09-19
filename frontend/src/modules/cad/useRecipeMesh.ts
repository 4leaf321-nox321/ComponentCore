/**
 * 도면이 바뀌면 검사하고, 맞으면 메시를 받아 온다 — 편집기(도면 · 조립)가 3D 미리보기에 쓴다.
 *
 * 500ms 쉬었다가 한 번만 묻고, 같은 도면은 다시 그리지 않는다. 빈 도면은 검사할 것이 없다 —
 * 「적어도 1개」 는 오류가 아니라 아직 시작 전이다.
 */

import { useEffect, useRef, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Recipe, RecipeSummary } from '@/modules/cad/api'
import { nodesOf } from '@/modules/cad/recipeSpec'
import type { MeshData } from '@/shared/viewer/PickViewer'

export function useRecipeMesh(value: Recipe) {
  const [problems, setProblems] = useState<string[]>([])
  const [summary, setSummary] = useState<RecipeSummary | null>(null)
  const [mesh, setMesh] = useState<MeshData | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const lastDrawn = useRef<string>('')

  useEffect(() => {
    if (nodesOf(value).length === 0) {
      setProblems([])
      setSummary(null)
      setMesh(null)
      lastDrawn.current = ''
      return
    }
    const key = JSON.stringify(value)
    const timer = setTimeout(async () => {
      try {
        const result = await cadApi.check(value)
        setProblems(result.problems)
        if (!result.ok || key === lastDrawn.current) return
        setDrawing(true)
        setError(null)
        try {
          const made = await cadApi.mesh(value)
          lastDrawn.current = key
          setSummary(made.summary)
          setMesh(made.mesh)
        } catch (caught) {
          setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
        } finally {
          setDrawing(false)
        }
      } catch {
        // 서버가 잠깐 안 닿는다 — 다음 변경에서 다시.
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [value])

  return { problems, summary, mesh, drawing, error }
}

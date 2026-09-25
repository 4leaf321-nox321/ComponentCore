/**
 * 도면이 바뀌면 검사하고, 맞으면 메시를 받아 온다 — 편집기(도면 · 조립)가 3D 미리보기에 쓴다.
 *
 * 500ms 쉬었다가 한 번만 묻고, 같은 도면은 다시 그리지 않는다. 빈 도면은 검사할 것이 없다 —
 * 「적어도 1개」 는 오류가 아니라 아직 시작 전이다.
 */

import { useEffect, useRef, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Interference, Recipe, RecipeSummary } from '@/modules/cad/api'
import { nodesOf } from '@/modules/cad/recipeSpec'
import type { FrameRow, MeshData } from '@/shared/viewer/PickViewer'

export function useRecipeMesh(value: Recipe, options: { interference?: boolean } = {}) {
  const [problems, setProblems] = useState<string[]>([])
  const [summary, setSummary] = useState<RecipeSummary | null>(null)
  const [mesh, setMesh] = useState<MeshData | null>(null)
  /** 레시피의 좌표계 — 서버가 지금 치수로 푼 원점 · 축(편집기가 3D 에 그린다). */
  const [frames, setFrames] = useState<FrameRow[]>([])
  /** 조립이면 구성품끼리 겹침 — `options.interference` 일 때만 묻는다. */
  const [interference, setInterference] = useState<Interference | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const lastDrawn = useRef<string>('')

  useEffect(() => {
    if (nodesOf(value).length === 0) {
      setProblems([])
      setSummary(null)
      setMesh(null)
      setFrames([])
      setInterference(null)
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
          setFrames(made.frames ?? [])
          if (options.interference) {
            // 메시 뒤에 따로 — 겹침은 불리언이라 느릴 수 있고, 그림이 먼저 보여야 한다.
            cadApi
              .interference(value)
              .then((got) => lastDrawn.current === key && setInterference(got))
              .catch(() => setInterference(null))
          }
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

  return { problems, summary, mesh, frames, drawing, error, interference }
}

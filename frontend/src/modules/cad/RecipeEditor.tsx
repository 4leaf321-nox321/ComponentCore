/**
 * 레시피 편집기 — 2단계에서는 JSON 텍스트 + 실시간 검증 + 미리보기.
 *
 * 3단계에서 피처 트리 · 스케치 캔버스가 이 자리에 온다. 그때도 이 컴포넌트의 계약(레시피 in →
 * 레시피 out, 문제 목록, 미리보기)은 그대로다 — 안쪽만 바뀐다.
 */

import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { Recipe, RecipeSummary } from '@/modules/cad/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Textarea } from '@/shared/components/ui/textarea'
import { VIEWER_COLORS } from '@/shared/viewer/colors'

const ModelViewer = lazy(() => import('@/shared/viewer/ModelViewer'))

export function pretty(recipe: Recipe): string {
  return JSON.stringify(recipe, null, 2)
}

export function RecipeEditor({
  value,
  onChange,
  actions,
}: {
  value: Recipe
  onChange: (recipe: Recipe) => void
  /** 편집기 위 오른쪽 — 저장 · 내려받기 같은 단추를 호출부가 준다. */
  actions?: React.ReactNode
}) {
  const [text, setText] = useState(() => pretty(value))
  const [problems, setProblems] = useState<string[]>([])
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [summary, setSummary] = useState<RecipeSummary | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const lastValue = useRef(value)

  // 바깥에서 레시피가 바뀌면(템플릿 고름 · 버전 고름) 글자도 바꾼다.
  useEffect(() => {
    if (value !== lastValue.current) {
      lastValue.current = value
      setText(pretty(value))
    }
  }, [value])

  // 칠 때마다 JSON 을 풀고, 풀리면 서버에 모양을 묻는다(디바운스).
  useEffect(() => {
    let parsed: Recipe
    try {
      parsed = JSON.parse(text) as Recipe
      setJsonError(null)
    } catch (caught) {
      setJsonError(caught instanceof Error ? caught.message : 'JSON 이 아닙니다')
      return
    }
    const timer = setTimeout(async () => {
      try {
        const result = await cadApi.check(parsed)
        setProblems(result.problems)
        if (result.ok) {
          lastValue.current = parsed
          onChange(parsed)
        }
      } catch {
        // 서버가 잠깐 안 닿는다 — 다음 입력에서 다시.
      }
    }, 400)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])

  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url)
  }, [url])

  async function draw() {
    setBusy(true)
    setError(null)
    try {
      const recipe = JSON.parse(text) as Recipe
      const [info, blob] = await Promise.all([cadApi.info(recipe), cadApi.preview(recipe)])
      setSummary(info.summary)
      setUrl((old) => {
        if (old) URL.revokeObjectURL(old)
        return URL.createObjectURL(blob)
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  const valid = !jsonError && problems.length === 0

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="space-y-2 lg:col-span-2">
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => void draw()} disabled={busy || !valid}>
            {busy ? '그리는 중…' : '그리기'}
          </Button>
          <div className="flex-1" />
          {actions}
        </div>
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          spellCheck={false}
          className="min-h-[420px] font-mono text-xs"
        />
        {jsonError && <p className="text-destructive text-xs">JSON: {jsonError}</p>}
        {problems.length > 0 && (
          <ul className="text-destructive list-inside list-disc text-xs">
            {problems.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        )}
        {valid && <p className="text-muted-foreground text-xs">레시피 모양이 맞습니다.</p>}
        <ErrorNotice error={error} />
        {summary && (
          <p className="text-muted-foreground text-xs">
            {summary.bbox.size.map((v) => v.toFixed(1)).join(' × ')} mm · 부피{' '}
            {summary.volume.toLocaleString()} mm³ · 면 {summary.face_count} · 노드 {summary.nodes.length}
            {summary.warnings.map((w) => (
              <span key={w} className="ml-2 text-amber-600">
                {w}
              </span>
            ))}
          </p>
        )}
      </div>
      <div className="lg:col-span-3">
        {url ? (
          <Suspense fallback={<Skeleton className="h-[480px] w-full" />}>
            <ModelViewer models={[{ url, color: VIEWER_COLORS.product }]} />
          </Suspense>
        ) : (
          <div className="text-muted-foreground flex h-[480px] items-center justify-center rounded-md border border-dashed text-sm">
            「그리기」 를 누르면 여기에 뜹니다.
          </div>
        )}
      </div>
    </div>
  )
}

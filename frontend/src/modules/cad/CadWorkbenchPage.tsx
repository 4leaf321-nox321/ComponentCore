/**
 * CAD 작업대 — 제품 파일 없이 기본 도형을 그린다.
 *
 * 종류와 치수를 넣으면 서버(build123d)가 만들어 glTF 로 보여 주고 STEP 으로 내려준다.
 * 여기서 만든 스펙은 지그 프로젝트의 「제품」 으로도 쓸 수 있다.
 */

import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cadApi } from '@/modules/cad/api'
import type { PrimitiveInfo } from '@/modules/cad/api'
import { jigsApi } from '@/modules/jigs/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import { VIEWER_COLORS } from '@/shared/viewer/colors'

const ModelViewer = lazy(() => import('@/shared/viewer/ModelViewer'))

const KIND_LABELS: Record<string, string> = {
  box: '상자',
  cylinder: '원기둥',
  plate_with_holes: '구멍 뚫린 판',
  bracket: 'L 브래킷',
}

const FIELD_LABELS: Record<string, string> = {
  length: '길이',
  width: '너비',
  height: '높이',
  thickness: '두께',
  radius: '반지름',
  hole_diameter: '구멍 지름',
  hole_margin: '구멍 여백',
}

export default function CadWorkbenchPage() {
  const navigate = useNavigate()
  const kinds = useResource(() => cadApi.kinds(), [])
  const [spec, setSpec] = useState<Record<string, unknown> | null>(null)
  const [info, setInfo] = useState<PrimitiveInfo | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (kinds.data && !spec) setSpec(kinds.data.examples.bracket ?? { kind: kinds.data.kinds[0] })
  }, [kinds.data, spec])

  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url)
  }, [url])

  async function draw() {
    if (!spec) return
    setBusy(true)
    setError(null)
    try {
      const [meta, blob] = await Promise.all([cadApi.info(spec), cadApi.glb(spec)])
      setInfo(meta)
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

  async function downloadStep() {
    if (!spec) return
    setError(null)
    try {
      const blob = await cadApi.step(spec)
      const href = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = href
      anchor.download = `${String(spec.kind)}.step`
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(href), 10_000)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  async function makeProject() {
    if (!spec) return
    setError(null)
    try {
      const made = await jigsApi.create({
        name: `${KIND_LABELS[String(spec.kind)] ?? String(spec.kind)} 지그`,
        description: 'CAD 작업대에서 만든 도형',
        product_spec: spec,
      })
      navigate(`/jigs/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  const fields = spec ? Object.keys(spec).filter((key) => key !== 'kind') : []

  return (
    <div className="space-y-4">
      <PageHeader
        title="CAD 작업대"
        description="제품 파일이 없어도 기본 도형을 그려 STEP 으로 받거나, 그대로 지그 프로젝트의 제품으로 씁니다."
      />
      <ErrorNotice error={error ?? kinds.error} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>도형</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label>종류</Label>
              <Select
                value={spec ? String(spec.kind) : ''}
                onValueChange={(kind) => {
                  setSpec(kinds.data?.examples[kind] ?? { kind })
                  setInfo(null)
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="종류" />
                </SelectTrigger>
                <SelectContent>
                  {(kinds.data?.kinds ?? []).map((kind) => (
                    <SelectItem key={kind} value={kind}>
                      {KIND_LABELS[kind] ?? kind}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {fields.map((key) => (
              <div key={key} className="space-y-1">
                <Label htmlFor={`f-${key}`}>{FIELD_LABELS[key] ?? key} (mm)</Label>
                <Input
                  id={`f-${key}`}
                  type="number"
                  step={0.5}
                  value={String(spec?.[key] ?? '')}
                  onChange={(event) =>
                    setSpec((old) => ({ ...old, [key]: Number(event.target.value) }))
                  }
                />
              </div>
            ))}
            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={() => void draw()} disabled={busy || !spec}>
                {busy ? '그리는 중…' : '그리기'}
              </Button>
              <Button variant="outline" onClick={() => void downloadStep()} disabled={!spec}>
                STEP 받기
              </Button>
              <Button variant="outline" onClick={() => void makeProject()} disabled={!spec}>
                이 도형으로 지그 프로젝트
              </Button>
            </div>
            {info && (
              <p className="text-muted-foreground text-xs">
                {info.bbox_size.map((v) => v.toFixed(1)).join(' × ')} mm · 부피{' '}
                {info.volume.toLocaleString()} mm³ · 면 {info.face_count}
              </p>
            )}
          </CardContent>
        </Card>

        <div className="lg:col-span-2">
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
    </div>
  )
}

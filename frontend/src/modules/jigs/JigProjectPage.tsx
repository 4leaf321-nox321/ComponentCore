/**
 * 프로젝트 상세 — 제품(STEP 또는 도형) · 옵션 · 실행 · 결과.
 *
 * 실행은 동기다: 단추를 누르면 서버가 파이프라인을 다 돌리고 결과를 돌려준다. 손바닥만 한
 * 부품은 1초 안쪽이다. 큰 조립체를 받기 시작하면 서버가 큐로 옮기고 여기가 폴링으로 바뀐다.
 */

import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { jigsApi } from '@/modules/jigs/api'
import type { JigRun } from '@/modules/jigs/api'
import { OptionsForm } from '@/modules/jigs/OptionsForm'
import { RunResult } from '@/modules/jigs/RunResult'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

const PRIMITIVE_LABELS: Record<string, string> = {
  box: '상자',
  cylinder: '원기둥',
  plate_with_holes: '구멍 뚫린 판',
  bracket: 'L 브래킷',
}

const NONE = '__none__'

export default function JigProjectPage() {
  const { id = '' } = useParams<{ id: string }>()
  const { user } = useAuth()
  const project = useResource(() => jigsApi.get(id), [id])
  const runs = useResource(() => jigsApi.runs(id), [id])
  const defaults = useResource(() => jigsApi.options(), [])
  const [options, setOptions] = useState<Record<string, unknown> | null>(null)
  const [selected, setSelected] = useState<JigRun | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState<'upload' | 'run' | null>(null)
  const [removingProduct, setRemovingProduct] = useState(false)
  const fileInput = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (defaults.data && !options) setOptions(defaults.data.defaults)
  }, [defaults.data, options])

  useEffect(() => {
    if (!selected && runs.data && runs.data.length > 0) setSelected(runs.data[0])
  }, [runs.data, selected])

  const p = project.data
  const editable = p ? canEditProject(user, p.owner_id) : false

  async function act(kind: 'upload' | 'run', work: () => Promise<unknown>) {
    setBusy(kind)
    setError(null)
    try {
      await work()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(null)
    }
  }

  async function upload(file: File) {
    await act('upload', async () => {
      await jigsApi.uploadProduct(id, file)
      project.reload()
    })
  }

  async function run() {
    await act('run', async () => {
      const made = await jigsApi.run(id, options ?? {})
      setSelected(made)
      runs.reload()
      project.reload()
    })
  }

  async function changeSpec(kind: string) {
    const spec = kind === NONE ? null : { kind }
    await act('upload', async () => {
      await jigsApi.update(id, { product_spec: spec })
      project.reload()
    })
  }

  if (project.error) return <ErrorNotice error={project.error} />
  if (!p) return null

  return (
    <div className="space-y-6">
      <PageHeader
        title={p.name}
        description={p.description || `소유자 ${p.owner_name} · ${shownDateTime(p.created_at)}`}
        back={{ to: '/jigs', label: '지그 프로젝트' }}
      />
      <ErrorNotice error={error} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>제품</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {p.has_product_file ? (
              <div>
                <p className="font-medium">{p.product_filename}</p>
                <p className="text-muted-foreground text-xs">
                  {((p.product_size_bytes ?? 0) / 1024).toFixed(0)} KB · STEP
                </p>
              </div>
            ) : (
              <p className="text-muted-foreground">
                STEP 이 없습니다. 아래 도형 중 하나를 제품으로 쓰거나, 비워 두면 시연 제품(L 브래킷)으로
                돕니다.
              </p>
            )}
            {editable && (
              <div className="flex flex-wrap gap-2">
                <input
                  ref={fileInput}
                  type="file"
                  accept=".step,.stp"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void upload(file)
                    event.target.value = ''
                  }}
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() => fileInput.current?.click()}
                >
                  {busy === 'upload' ? '올리는 중…' : p.has_product_file ? 'STEP 바꾸기' : 'STEP 올리기'}
                </Button>
                {p.has_product_file && (
                  <Button size="sm" variant="ghost" onClick={() => setRemovingProduct(true)}>
                    파일 지우기
                  </Button>
                )}
              </div>
            )}
            {!p.has_product_file && (
              <div className="space-y-1">
                <p className="text-muted-foreground text-xs">파일 대신 기본 도형</p>
                <Select
                  value={p.product_spec ? String(p.product_spec.kind) : NONE}
                  onValueChange={(value) => void changeSpec(value)}
                  disabled={!editable || busy !== null}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>(없음 — 시연 제품)</SelectItem>
                    {(defaults.data?.primitive_kinds ?? []).map((kind) => (
                      <SelectItem key={kind} value={kind}>
                        {PRIMITIVE_LABELS[kind] ?? kind}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-muted-foreground text-xs">
                  치수까지 정하려면 CAD 작업대에서 그린 스펙을 쓰세요.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>생성 옵션</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {options && <OptionsForm values={options} onChange={setOptions} />}
            <div className="flex items-center gap-2">
              <Button onClick={() => void run()} disabled={busy !== null || !options}>
                {busy === 'run' ? '만드는 중…' : '지그 생성'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => defaults.data && setOptions(defaults.data.defaults)}
              >
                기본값으로
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>실행 기록</CardTitle>
          </CardHeader>
          <CardContent>
            {(runs.data ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">아직 만든 지그가 없습니다.</p>
            ) : (
              <ul className="space-y-1">
                {(runs.data ?? []).map((one) => (
                  <li key={one.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(one)}
                      className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm ${
                        selected?.id === one.id ? 'bg-accent' : 'hover:bg-accent/60'
                      }`}
                    >
                      <span>{shownDateTime(one.started_at)}</span>
                      <StatusBadge kind="run" value={one.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <div className="lg:col-span-3">
          {selected ? (
            <RunResult run={selected} />
          ) : (
            <EmptyState
              title="결과가 없습니다"
              hint="「지그 생성」 을 누르면 여기에 3D 와 계획이 뜹니다."
            />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={removingProduct}
        title="제품 파일을 지웁니다"
        description="올린 STEP 이 저장소에서 지워집니다. 이미 만든 지그 결과는 남습니다."
        confirmLabel="지우기"
        destructive
        onConfirm={async () => {
          await jigsApi.removeProduct(id)
          setRemovingProduct(false)
          project.reload()
        }}
        onClose={() => setRemovingProduct(false)}
      />
    </div>
  )
}

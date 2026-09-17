/** 부품 하나 — 버전 이력 · 3D · STEP · 이 부품의 지그들 · 내 공간으로 복사. */

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { GeometryJobView } from '@/modules/cad/GeometryJobView'
import { jigsApi } from '@/modules/jigs/api'
import { partsApi } from '@/modules/parts/api'
import type { PartVersion } from '@/modules/parts/api'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

export default function PartPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const part = useResource(() => partsApi.get(id), [id])
  const versions = useResource(() => partsApi.versions(id), [id])
  const jigs = useResource(() => jigsApi.list({ part_id: id }), [id])
  const [selected, setSelected] = useState<PartVersion | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!selected && part.data?.current) setSelected(part.data.current)
  }, [part.data, selected])

  const p = part.data
  if (part.error) return <ErrorNotice error={part.error} />
  if (!p) return null
  const editable = canEditProject(user, p.owner_id)

  async function copy(number?: number) {
    setBusy(true)
    setError(null)
    try {
      const made = await partsApi.copyToWork(id, { number })
      navigate(`/works/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={p.name}
        description={p.description || `${p.owner_name} · v${p.current_version} · ${shownDateTime(p.updated_at)}`}
        back={{ to: '/parts', label: '부품' }}
        actions={
          <>
            <Button variant="outline" onClick={() => void copy(selected?.number)} disabled={busy}>
              내 공간으로 복사{selected && selected.number !== p.current_version ? ` (v${selected.number})` : ''}
            </Button>
            {editable && (
              <Button variant="ghost" onClick={() => setDeleting(true)} disabled={busy}>
                내리기
              </Button>
            )}
          </>
        }
      />
      <ErrorNotice error={error} />

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="space-y-4 lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle>버전</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1">
                {(versions.data ?? []).map((one) => (
                  <li key={one.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(one)}
                      className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${selected?.id === one.id ? 'bg-accent' : 'hover:bg-accent/60'}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium">
                          v{one.number}
                          {one.number === p.current_version && <span className="text-muted-foreground ml-1 text-xs">현재</span>}
                        </span>
                        {one.job && <StatusBadge kind="run" value={one.job.status} />}
                      </div>
                      <p className="text-muted-foreground truncate text-xs">{one.note || '—'}</p>
                      <p className="text-muted-foreground text-xs">
                        {one.promoted_by_name} · {shownDateTime(one.created_at)}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>이 부품의 지그</CardTitle>
            </CardHeader>
            <CardContent>
              {(jigs.data?.items ?? []).length === 0 ? (
                <p className="text-muted-foreground text-sm">아직 없습니다.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {(jigs.data?.items ?? []).map((one) => (
                    <li key={one.id}>
                      <Link to={`/jigs/${one.id}`} className="hover:underline">
                        {one.name} <span className="text-muted-foreground text-xs">v{one.current_version}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="lg:col-span-3">
          {selected && (
            <GeometryJobView key={selected.id} job={selected.job} title={`v${selected.number}`} stepName={`${p.name}-v${selected.number}.step`} />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={deleting}
        title="부품을 내립니다"
        description={`「${p.name}」 이 카탈로그에서 사라집니다. 이 부품을 가리키는 지그는 남지만 부품 연결이 풀립니다.`}
        confirmLabel="내리기"
        destructive
        onConfirm={async () => {
          await partsApi.remove(id)
          navigate('/parts')
        }}
        onClose={() => setDeleting(false)}
      />
    </div>
  )
}

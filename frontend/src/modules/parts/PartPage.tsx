/** 부품 하나 — 버전 이력 · 3D · STEP · 해석 조건 · 이 부품의 지그들 · 내 공간으로 복사. */

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { GeometryJobView } from '@/modules/cad/GeometryJobView'
import { jigsApi } from '@/modules/jigs/api'
import { partsApi } from '@/modules/parts/api'
import type { PartVersion } from '@/modules/parts/api'
import { SimilarCard } from '@/modules/search/SimilarCard'
import { hasConditions } from '@/modules/works/DuplicateDialog'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { FolderLine } from '@/shared/folders/FolderParts'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

/** 조건 묶음의 이름 — 서버 조건 명세(`core/conditions.spec`)의 말과 같다. */
const CONDITION_GROUPS: [string, string][] = [
  ['named_selections', '선택 그룹'],
  ['materials', '물성'],
  ['constraints', '구속'],
  ['loads', '하중'],
  ['contacts', '접촉'],
  ['initial', '초기조건'],
  ['mesh_hints', '국부 메시'],
  ['body_settings', '파트별 설정'],
]

/** 등록할 때 함께 올린 해석 조건 — 무엇이 몇 개인지만. 복사하면 그대로 옮겨진다. */
function ConditionsCard({ conditions }: { conditions: Record<string, unknown> | undefined }) {
  const counts = CONDITION_GROUPS.map(([key, label]) => {
    const value = conditions?.[key]
    return [label, Array.isArray(value) ? value.length : 0] as const
  }).filter(([, count]) => count > 0)
  return (
    <Card>
      <CardHeader>
        <CardTitle>해석 조건</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        {hasConditions(conditions) && counts.length > 0 ? (
          <>
            <p>{counts.map(([label, count]) => `${label} ${count}`).join(' · ')}</p>
            <p className="text-muted-foreground text-xs">내 작업 공간으로 복사하면 해석 조건도 함께 복사됩니다.</p>
          </>
        ) : (
          <p className="text-muted-foreground">이 버전에는 등록된 해석 조건이 없습니다.</p>
        )}
      </CardContent>
    </Card>
  )
}

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
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
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
              내 작업 공간으로 복사{selected && selected.number !== p.current_version ? ` (v${selected.number})` : ''}
            </Button>
            {editable && (
              <Button variant="ghost" onClick={() => setDeleting(true)} disabled={busy}>
                등록 해제
              </Button>
            )}
          </>
        }
      />
      <ErrorNotice error={error} />
      <FolderLine
        folder={p.folder}
        editable={editable}
        suggestions={partsApi.folders}
        onMove={async (folder) => {
          await partsApi.update(id, { folder })
          part.reload()
        }}
      />

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
                <p className="text-muted-foreground text-sm">등록된 지그가 없습니다.</p>
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
          {selected && <ConditionsCard conditions={selected.conditions} />}
          {p.current_version > 0 && <SimilarCard source={`part:${id}`} />}
        </div>
        <div className="lg:col-span-3">
          {selected && (
            <GeometryJobView key={selected.id} job={selected.job} title={`v${selected.number}`} stepName={`${p.name}-v${selected.number}.step`} />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={deleting}
        title="부품 등록을 해제하시겠습니까?"
        description={`‘${p.name}’이(가) 카탈로그에서 삭제됩니다. 이 부품을 참조하는 지그는 유지되지만 부품 연결은 해제됩니다.`}
        confirmLabel="등록 해제"
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

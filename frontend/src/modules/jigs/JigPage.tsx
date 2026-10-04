/** 지그 하나 — 버전 이력 · 결과(3D · 계획 · 간섭 · STEP) · 해석 조건 · 어느 부품 버전의 지그인가 · 내 공간으로 복사. */

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ConditionsCard } from '@/modules/conditions/ConditionsCard'
import { jigsApi } from '@/modules/jigs/api'
import type { JigVersion } from '@/modules/jigs/api'
import { JigResultView } from '@/modules/jigs/JigResultView'
import { SimilarCard } from '@/modules/search/SimilarCard'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ApiError } from '@/shared/api/client'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { FolderLine } from '@/shared/folders/FolderParts'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

export default function JigPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const jig = useResource(() => jigsApi.get(id), [id])
  const versions = useResource(() => jigsApi.versions(id), [id])
  const [selected, setSelected] = useState<JigVersion | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!selected && jig.data?.current) setSelected(jig.data.current)
  }, [jig.data, selected])

  const j = jig.data
  if (jig.error) return <ErrorNotice error={jig.error} />
  if (!j) return null
  const editable = canEditProject(user, j.owner_id)

  /** 남의 지그를 고치거나 그 지그로 DOE 를 돌리는 길 — 레시피 · 잡는 부품 · 해석 조건이 따라간다. */
  async function copy(number?: number) {
    setBusy(true)
    setError(null)
    try {
      const made = await jigsApi.copyToWork(id, { number })
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
        title={j.name}
        description={
          <>
            {j.part_id ? (
              <>
                부품{' '}
                <Link to={`/parts/${j.part_id}`} className="hover:underline">
                  {j.part_name}
                </Link>
                {selected?.part_version != null && ` v${selected.part_version}`}의 지그
              </>
            ) : (
              '제품 스냅숏 기반 지그'
            )}
            {' · '}
            {j.owner_name} · {shownDateTime(j.updated_at)}
          </>
        }
        back={{ to: '/jigs', label: '지그' }}
        actions={
          <>
            {j.work_id && user?.id === j.owner_id && (
              <Button variant="outline" onClick={() => navigate(`/works/${j.work_id}`)}>
                원본 작업 열기
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => void copy(selected?.number)}
              disabled={busy || !selected?.recipe}
              title={selected && !selected.recipe ? '생성기로 만든 이전 버전이라 레시피가 없어 복사할 수 없습니다.' : undefined}
            >
              내 작업 공간으로 복사{selected && selected.number !== j.current_version ? ` (v${selected.number})` : ''}
            </Button>
            {editable && (
              <Button variant="ghost" onClick={() => setDeleting(true)}>
                등록 해제
              </Button>
            )}
          </>
        }
      />

      <ErrorNotice error={error} />
      <FolderLine
        folder={j.folder}
        editable={editable}
        suggestions={jigsApi.folders}
        onMove={async (folder) => {
          await jigsApi.update(id, { folder })
          jig.reload()
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
                          {one.number === j.current_version && <span className="text-muted-foreground ml-1 text-xs">현재</span>}
                        </span>
                        {one.part_version != null && <span className="text-muted-foreground text-xs">부품 v{one.part_version}</span>}
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
          {selected && <ConditionsCard conditions={selected.conditions} />}
          {j.current_version > 0 && <SimilarCard source={`jig:${id}`} />}
        </div>
        <div className="lg:col-span-3">
          {selected?.job ? (
            <JigResultView key={selected.id} job={selected.job} />
          ) : (
            <EmptyState title="결과 파일이 없습니다" hint="이 버전의 생성 작업이 삭제되었습니다. 계획 요약만 남아 있습니다." />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={deleting}
        title="지그 등록을 해제하시겠습니까?"
        description={`‘${j.name}’이(가) 카탈로그에서 삭제됩니다. 원본 작업과 부품은 유지됩니다.`}
        confirmLabel="등록 해제"
        destructive
        onConfirm={async () => {
          await jigsApi.remove(id)
          navigate('/jigs')
        }}
        onClose={() => setDeleting(false)}
      />
    </div>
  )
}

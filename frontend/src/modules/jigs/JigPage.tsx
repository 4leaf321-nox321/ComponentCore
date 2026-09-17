/** 지그 하나 — 버전 이력 · 결과(3D · 계획 · 간섭 · STEP) · 어느 부품 버전의 지그인가. */

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { jigsApi } from '@/modules/jigs/api'
import type { JigVersion } from '@/modules/jigs/api'
import { JigResultView } from '@/modules/jigs/JigResultView'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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

  useEffect(() => {
    if (!selected && jig.data?.current) setSelected(jig.data.current)
  }, [jig.data, selected])

  const j = jig.data
  if (jig.error) return <ErrorNotice error={jig.error} />
  if (!j) return null
  const editable = canEditProject(user, j.owner_id)

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
                {selected?.part_version != null && ` v${selected.part_version}`} 의 지그
              </>
            ) : (
              '제품 스냅숏만 있는 지그'
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
                원본 작업으로
              </Button>
            )}
            {editable && (
              <Button variant="ghost" onClick={() => setDeleting(true)}>
                내리기
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-1">
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
        <div className="lg:col-span-3">
          {selected?.job ? (
            <JigResultView key={selected.id} job={selected.job} />
          ) : (
            <EmptyState title="결과 파일이 없습니다" hint="이 버전의 생성 작업이 지워졌습니다. 계획 요약만 남아 있습니다." />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={deleting}
        title="지그를 내립니다"
        description={`「${j.name}」 이 카탈로그에서 사라집니다. 원본 작업과 부품은 남습니다.`}
        confirmLabel="내리기"
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

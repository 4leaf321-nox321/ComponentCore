/**
 * DOE 하나 — 설계점 표와 공유 폴더. 설정을 바꿔 다시 만드는 길도 여기서 연다.
 *
 * **남의 DOE 는 보기만 된다**(보내기 · 점 추가 · 재생성은 소유자만). 이어서 하려는 사람은
 * 「내 것으로 복제」 — 같은 설계점 · 해석 조건으로 자기 DOE 를 갖는다. 공용 부품의 「내 작업
 * 공간으로 복사」 와 같은 규칙이다.
 */

import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject } from '@/shared/auth/roles'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

export default function DoeStudyPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const study = useResource(() => doeApi.get(id), [id])
  /** 복제 대화상자 — 열려 있으면 새 이름. */
  const [cloneName, setCloneName] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  if (study.error) return <ErrorNotice error={study.error} />
  if (!study.data) return <Skeleton className="h-64 w-full" />
  const s = study.data
  const editable = canEditProject(user, s.owner_id ?? '')

  async function clone() {
    setBusy(true)
    setError(null)
    try {
      const made = await doeApi.clone(s.id, cloneName?.trim() || undefined)
      setCloneName(null)
      navigate(`/doe/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        title={s.name}
        description={s.description || '변수를 탐색하여 생성한 형상입니다.'}
        back={{ to: '/doe', label: 'DOE 목록' }}
        actions={
          <>
            {/* 만든 것은 그대로 두고, 이 설정을 채워 넣은 새 DOE 를 만든다 — 범위를 좁혀 다시 돌릴 때. 대상 작업을 여니 소유자만. */}
            {editable && (
              <Button variant="outline" onClick={() => navigate(`/doe/new?from=${s.id}`)}>
                설정 변경 후 새 DOE 생성
              </Button>
            )}
            <Button variant={editable ? 'outline' : 'default'} onClick={() => setCloneName(`${s.name} (복제)`)}>
              {editable ? '복제' : '내 것으로 복제'}
            </Button>
          </>
        }
      />
      {s.cloned_from_id && (
        <p className="text-muted-foreground mb-2 text-sm">
          <Link to={`/doe/${s.cloned_from_id}`} className="hover:underline">
            ‘{s.cloned_from_name}’
          </Link>
          에서 복제한 DOE입니다. 설계점 번호와 값이 원본과 같습니다.
        </p>
      )}
      {!editable && (
        <p role="note" className="bg-muted/40 mb-3 rounded-md border p-3 text-sm">
          {s.owner_name}의 DOE입니다. 조회만 가능합니다. 이어서 작업하려면 ‘내 것으로 복제’를 클릭하십시오. 같은 설계점과 해석 조건으로 내 DOE가 생성되며, 원본은 변경되지 않습니다.
        </p>
      )}
      <DoeStudyView study={s} onReload={study.reload} editable={editable} />

      <Dialog open={cloneName !== null} onOpenChange={(open) => !open && !busy && setCloneName(null)}>
        <DialogContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void clone()
            }}
            className="space-y-4"
          >
            <DialogHeader>
              <DialogTitle>{editable ? 'DOE 복제' : '내 것으로 복제'}</DialogTitle>
              <DialogDescription>
                같은 설계점({s.point_count}개)과 해석 조건으로 내 소유의 새 DOE를 생성하고 형상을 다시 생성합니다. 원본은 변경되지 않습니다.
                {!editable && ' 대상 작업은 다른 사용자의 것이므로 연결하지 않고 도면 스냅샷으로 생성합니다.'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="clone-name">이름</Label>
              <Input id="clone-name" value={cloneName ?? ''} onChange={(e) => setCloneName(e.target.value)} autoFocus />
            </div>
            <ErrorNotice error={error} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCloneName(null)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? '복제 중…' : '복제'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

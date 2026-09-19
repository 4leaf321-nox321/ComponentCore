/** DOE 하나 — 설계점 표와 공유 폴더. 설정을 바꿔 다시 만드는 길도 여기서 연다. */

import { useNavigate, useParams } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

export default function DoeStudyPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const study = useResource(() => doeApi.get(id), [id])

  if (study.error) return <ErrorNotice error={study.error} />
  if (!study.data) return <Skeleton className="h-64 w-full" />

  return (
    <div>
      <PageHeader
        title={study.data.name}
        description={study.data.description || '변수를 훑어 만든 형상들'}
        back={{ to: '/doe', label: 'DOE 목록' }}
        actions={
          // 만든 것은 그대로 두고, 이 설정을 채워 넣은 새 DOE 를 만든다 — 범위를 좁혀 다시 돌릴 때.
          <Button variant="outline" onClick={() => navigate(`/doe/new?from=${study.data!.id}`)}>
            설정 바꿔 다시 만들기
          </Button>
        }
      />
      <DoeStudyView study={study.data} onReload={study.reload} />
    </div>
  )
}

/** 실험계획 하나 — 설계점 표와 공유 폴더. */

import { useParams } from 'react-router-dom'

import { doeApi } from '@/modules/doe/api'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

export default function DoeStudyPage() {
  const { id = '' } = useParams()
  const study = useResource(() => doeApi.get(id), [id])

  if (study.error) return <ErrorNotice error={study.error} />
  if (!study.data) return <Skeleton className="h-64 w-full" />

  return (
    <div>
      <PageHeader
        title={study.data.name}
        description={study.data.description || '치수를 훑어 만든 형상들'}
        back={{ to: '/doe', label: '실험계획 목록' }}
      />
      <DoeStudyView study={study.data} onReload={study.reload} />
    </div>
  )
}

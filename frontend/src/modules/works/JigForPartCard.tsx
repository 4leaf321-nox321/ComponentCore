/**
 * 지그 작업의 덤 — **이 지그가 잡는 부품**.
 *
 * 지그를 그리는 데에는 필요 없지만, 이어 두면 두 가지가 된다: 승격할 때 「어느 부품의 지그인가」
 * 가 자동으로 따라가고, 제품 치수를 보러 갈 곳이 생긴다. 안 이어도 그리는 데는 지장이 없다 —
 * **그리기를 막는 칸이 아니다.**
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { partsApi } from '@/modules/parts/api'
import { worksApi } from '@/modules/works/api'
import type { Work } from '@/modules/works/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'

const NONE = '__none__'

export function JigForPartCard({ work, onSaved }: { work: Work; onSaved: () => void }) {
  const parts = useResource(() => partsApi.list(0, 100), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function save(partId: string | null) {
    setBusy(true)
    setError(null)
    try {
      await worksApi.update(work.id, { jig_for_part_id: partId })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>잡는 부품</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={work.jig_for_part_id ?? NONE}
            onValueChange={(value) => void save(value === NONE ? null : value)}
            disabled={busy}
          >
            <SelectTrigger className="w-72">
              <SelectValue placeholder="고르지 않음" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>고르지 않음 — 홀로 선 지그</SelectItem>
              {(parts.data?.items ?? []).map((one) => (
                <SelectItem key={one.id} value={one.id}>
                  {one.name} (v{one.current_version})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {work.jig_for_part_id && (
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/parts/${work.jig_for_part_id}`}>부품 보기</Link>
            </Button>
          )}
        </div>
        <p className="text-muted-foreground text-xs">
          이어 두면 승격할 때 「어느 부품의 지그인가」 가 따라갑니다. 제품 형상을 지그 안으로 불러오려면 부품 화면에서 STEP 을 받아 「STEP 올리기」 하거나, 레시피에 <code>import_step</code> 으로 넣습니다.
        </p>
        <ErrorNotice error={error ?? parts.error} />
      </CardContent>
    </Card>
  )
}

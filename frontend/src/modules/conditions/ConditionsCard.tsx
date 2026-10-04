/**
 * 등록할 때 함께 올린 **해석 조건** — 무엇이 몇 개인지만. 공용 부품 · 지그 화면이 쓴다.
 * 「내 작업 공간으로 복사」 가 조건까지 옮기므로, 복사하기 전에 무엇이 따라오는지 보인다.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'

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

export function ConditionsCard({ conditions }: { conditions: Record<string, unknown> | undefined }) {
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
        {counts.length > 0 ? (
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

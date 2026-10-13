/**
 * 부품 · 지그 상세의 「기준정보」 — **이 부품(지그)을 가리키는 온톨로지 객체.**
 *
 * 부품 · 지그는 온톨로지의 원 표다(`kind_class='system'`, 백엔드 `parts/system.py` ·
 * `jigs/system.py`, ADR 0008). SP 에서 받은 제품 · 프로젝트가 관계로 이 부품을 가리키면 그 선이
 * 여기 선다. 잇고 끊는 것은 기준정보 쪽 상세(`/o/<타입>/<id>`)의 일이다 — 같은 화면을 두 벌 만들면
 * 권한 · 개수 제약이 갈린다.
 *
 * 원 표를 비추는 타입이 아직 없으면 시스템 관리자에게만 만드는 자리를 알린다 — 못 만드는 사람에게
 * 띄우면 못 지우는 안내가 된다.
 */

import { Link } from 'react-router-dom'

import { objectApi } from '@/modules/objects/api'
import { ontologyApi } from '@/modules/ontology/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { useResource } from '@/shared/hooks/useResource'

/** 원 표의 키(백엔드 `SystemSource.key`) → 화면에 적을 이름과 목적격. */
const NOUNS = {
  part: { noun: '부품', object: '부품을' },
  jig: { noun: '지그', object: '지그를' },
} as const

/**
 * 원 표의 행을 고치는 CompCore 화면 — 기준정보 쪽 상세(`ObjectProfilePage`)가 「그 표의 화면」 으로
 * 보낼 곳. 여기 없는 원 표(부서 · 계정)는 SP 처럼 안내 문장만 남는다.
 */
export function sourceScreen(source: string, id: string): string | null {
  if (source === 'part') return `/parts/${id}`
  if (source === 'jig') return `/jigs/${id}`
  return null
}

interface Props {
  source: keyof typeof NOUNS
  id: string
}

export function SourceLinksCard({ source, id }: Props) {
  const { noun, object } = NOUNS[source]
  const { user } = useAuth()
  const schema = useResource(() => ontologyApi.schema(), [])
  // **곁 카드가 부품 화면을 쓰러뜨리지 않게** — 스키마가 이상하면 카드만 비운다.
  const types = Array.isArray(schema.data?.types) ? schema.data.types : []
  const typeSlug = types.find((one) => one.kind_class === 'system' && one.system_source === source)?.slug
  const profile = useResource(
    () => (typeSlug ? objectApi.profile(typeSlug, id) : Promise.resolve(null)),
    [typeSlug, id],
  )

  if (!schema.data) return null
  if (!typeSlug) {
    if (!isSystemAdmin(user)) return null
    return (
      <Card>
        <CardHeader>
          <CardTitle>기준정보</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          관리 › 온톨로지 › 타입에서 원 표가 「{noun}」인 시스템 타입을 만들면, 기준정보(SP 에서 받은 제품 ·
          프로젝트 등)가 이 {object} 가리킬 수 있습니다.{' '}
          <Link to="/admin/ontology/types" className="underline">
            타입 관리로
          </Link>
        </CardContent>
      </Card>
    )
  }

  const related = Array.isArray(profile.data?.related) ? profile.data.related : []
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle>기준정보</CardTitle>
        <Link to={`/o/${typeSlug}/${id}`} className="text-muted-foreground text-xs hover:underline">
          잇기 · 끊기 →
        </Link>
      </CardHeader>
      <CardContent>
        {profile.error ? (
          <p className="text-muted-foreground text-sm">기준정보를 불러오지 못했습니다.</p>
        ) : related.length === 0 ? (
          <p className="text-muted-foreground text-sm">이 {object} 가리키는 기준정보가 없습니다.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {related.map((one) => (
              <li key={one.relation_id} className="flex items-baseline gap-2">
                <span className="text-muted-foreground shrink-0 text-xs">{one.label}</span>
                <Link to={`/o/${one.object_type_slug}/${one.object_id}`} className="truncate hover:underline">
                  {one.object_label}
                </Link>
                <span className="text-muted-foreground ml-auto shrink-0 text-xs">{one.object_type_label}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

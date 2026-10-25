/**
 * 태그 거르개 — **타입별로** 묶은 칩(ADR 0011). 작업 · 부품 · 지그 · DOE 목록이 같이 쓴다.
 *
 * 태그는 온톨로지의 객체라 이름이 같아도 다른 것일 수 있다 — 고객사 「A」 와 프로젝트 「A」. 그래서
 * 이름이 아니라 **객체**로 거른다(`?tag_id=`). 「일반 태그」 는 타입 이름 없이 맨 앞에, 다른 타입은
 * 「고객사」 처럼 이름을 앞세워 묶는다. 칩 곁의 수는 붙은 곳이다.
 *
 * 고른 것을 다시 누르면 푼다(글자 거르개 `TagFilter` 와 같다). 태그가 하나도 없으면 아무것도 안
 * 그린다 — 누를 것이 없는 줄은 없느니만 못하다.
 */

import { DEFAULT_TAG_TYPE } from '@/modules/tagging/api'
import type { TagUse } from '@/modules/tagging/api'

export function TypedTagFilter({
  tags,
  value,
  onChange,
  label = '태그',
}: {
  tags: TagUse[]
  /** 고른 태그 객체의 id. 빈 문자열이면 안 거른다. */
  value: string
  onChange: (next: string) => void
  label?: string
}) {
  // **목록이 아니면 아무것도 안 그린다** — 한 응답이 이상하다고 목록 화면이 죽으면 안 된다.
  const rows = Array.isArray(tags) ? tags : []
  if (rows.length === 0) return null
  // 서버가 「일반 태그」 → 타입 이름 순으로 준다 — 그 차례대로 묶는다.
  const groups: { slug: string; label: string; items: TagUse[] }[] = []
  for (const one of rows) {
    const last = groups[groups.length - 1]
    if (last && last.slug === one.type_slug) last.items.push(one)
    else groups.push({ slug: one.type_slug, label: one.type_label, items: [one] })
  }
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      {groups.map((group) => (
        <span key={group.slug} className="inline-flex flex-wrap items-center gap-1" role="group" aria-label={group.label}>
          {group.slug !== DEFAULT_TAG_TYPE && <span className="text-muted-foreground text-xs">{group.label}:</span>}
          {group.items.map((one) => {
            const on = value === one.object_id
            return (
              <button
                key={one.object_id}
                type="button"
                onClick={() => onChange(on ? '' : one.object_id)}
                aria-pressed={on}
                title={`${one.type_label} · ${one.uses}곳`}
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  on ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
                }`}
              >
                {one.label}
                <span className={`ml-1 ${on ? 'opacity-80' : 'text-muted-foreground'}`}>{one.uses}</span>
              </button>
            )
          })}
        </span>
      ))}
    </div>
  )
}

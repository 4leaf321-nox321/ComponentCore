/**
 * 꼬리표 거르개 — **한 벌만 둔다.**
 *
 * 내 작업 · 부품 · 지그 · 템플릿이 같은 물음에 답한다: 「이 꼬리표가 붙은 것만」. 화면마다
 * 따로 그리면 한쪽만 고쳐지고, 그때부터 자리마다 다르게 동작한다.
 *
 * 꼬리표가 하나도 없으면 **아무것도 안 그린다** — 누를 것이 없는 줄은 없느니만 못하다.
 */

export function TagFilter({
  tags,
  value,
  onChange,
  label = '꼬리표',
}: {
  tags: string[]
  /** 지금 고른 것. 빈 문자열이면 안 거른다. */
  value: string
  onChange: (next: string) => void
  label?: string
}) {
  // **목록이 아니면 아무것도 안 그린다.** 한 응답이 이상하다고 페이지가 통째로 죽으면,
  // 꼬리표 하나 때문에 부품 목록을 못 보게 된다.
  const 있는것 = Array.isArray(tags) ? tags : []
  if (있는것.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="text-muted-foreground text-xs">{label}</span>
      {있는것.map((one) => (
        <button
          key={one}
          type="button"
          // 고른 것을 다시 누르면 푼다 — 끄는 길이 켜는 길과 같아야 헤매지 않는다.
          onClick={() => onChange(value === one ? '' : one)}
          aria-pressed={value === one}
          className={`rounded-full border px-2 py-0.5 text-xs ${
            value === one ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
          }`}
        >
          {one}
        </button>
      ))}
    </div>
  )
}

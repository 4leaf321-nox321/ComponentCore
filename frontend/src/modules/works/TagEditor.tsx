/** 꼬리표 — 프로젝트 · 제품군 같은 묶음. 칩으로 보이고, 치고 Enter 로 더하고, × 로 뗀다. */

import { X } from 'lucide-react'
import { useState } from 'react'

export function TagEditor({ tags, suggestions = [], onChange, busy }: { tags: string[]; suggestions?: string[]; onChange: (next: string[]) => void; busy?: boolean }) {
  const [text, setText] = useState('')
  const rest = suggestions.filter((one) => !tags.includes(one))
  function add(raw: string) {
    const tag = raw.trim().slice(0, 40)
    if (!tag || tags.includes(tag)) return
    onChange([...tags, tag])
    setText('')
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((one) => (
        <span key={one} className="bg-accent inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
          {one}
          <button type="button" className="text-muted-foreground hover:text-destructive" onClick={() => onChange(tags.filter((t) => t !== one))} disabled={busy} aria-label={`${one} 떼기`}>
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            add(text)
          }
        }}
        onBlur={() => text && add(text)}
        placeholder={tags.length === 0 ? '꼬리표 (Enter)' : '+'}
        className="h-6 min-w-20 bg-transparent px-1 text-xs outline-none"
        list="tag-suggestions"
        aria-label="꼬리표 더하기"
        disabled={busy}
      />
      {rest.length > 0 && (
        <datalist id="tag-suggestions">
          {rest.map((one) => (
            <option key={one} value={one} />
          ))}
        </datalist>
      )}
    </div>
  )
}

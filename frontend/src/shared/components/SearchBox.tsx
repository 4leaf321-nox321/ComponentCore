/** 목록 위의 찾기 칸 — 치면 조금 쉬었다가 묻는다(글자마다 서버를 부르지 않게). */

import { Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Input } from '@/shared/components/ui/input'

export function SearchBox({ value, onChange, placeholder = '이름 · 설명으로 찾기', className }: { value: string; onChange: (next: string) => void; placeholder?: string; className?: string }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  useEffect(() => {
    if (text === value) return
    const timer = setTimeout(() => onChange(text), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])
  return (
    <div className={`relative ${className ?? 'w-64'}`}>
      <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
      <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} className="h-8 pr-7 pl-7 text-sm" aria-label="찾기" />
      {text && (
        <button type="button" className="text-muted-foreground hover:text-foreground absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-0.5" onClick={() => setText('')} aria-label="찾기 지우기">
          <X className="size-3.5" />
        </button>
      )}
    </div>
  )
}

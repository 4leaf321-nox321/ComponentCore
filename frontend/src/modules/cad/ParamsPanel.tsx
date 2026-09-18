/**
 * 치수 — 이름 붙인 값. **파라메트릭 모델링의 손잡이**다.
 *
 * 여기 「판_길이 80」 을 두고 칸에 `=판_길이` 라고 쓰면, 이 값 하나만 고쳐도 그것을 쓰는 곳이
 * 모두 따라온다. 스케치 구속 솔버는 없지만, 치수 이름 + 기준 자리(`align`)로 지그가 필요로 하는
 * 「한쪽 고정, 반대쪽 늘리기」 는 된다.
 */

import { Plus, Ruler, Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'

export function ParamsPanel({ value, onChange }: { value: Recipe; onChange: (next: Recipe) => void }) {
  const params = (value.params ?? {}) as Record<string, number>
  const names = Object.keys(params)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')

  function put(next: Record<string, number>) {
    onChange({ ...value, params: next })
  }

  function rename(from: string, to: string) {
    const trimmed = to.trim()
    if (!trimmed || trimmed === from || trimmed in params) return
    // 이름을 바꾸면 그것을 쓰던 식도 따라 바꾼다 — 안 그러면 레시피가 통째로 깨진다.
    const pattern = new RegExp(`(?<![\\w])${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w])`, 'g')
    const swapped = JSON.parse(
      JSON.stringify(value.nodes).replaceAll(/"=[^"]*"/g, (found) => found.replaceAll(pattern, trimmed)),
    ) as Recipe['nodes']
    const next: Record<string, number> = {}
    for (const key of names) next[key === from ? trimmed : key] = params[key]
    onChange({ ...value, params: next, nodes: swapped })
  }

  return (
    <div className="mb-2 rounded-md border p-2">
      <div className="mb-1 flex items-center gap-1">
        <Ruler className="text-muted-foreground size-3.5" />
        <span className="text-xs font-medium">치수</span>
        <span className="text-muted-foreground truncate text-[11px]">칸에 「=이름」 으로 씁니다</span>
        <Button size="sm" variant="ghost" className="ml-auto h-6 px-1" onClick={() => setAdding(true)} aria-label="치수 더하기">
          <Plus className="size-3.5" />
        </Button>
      </div>
      {names.length === 0 && !adding && (
        <p className="text-muted-foreground text-[11px]">
          없습니다. 「판_길이」 처럼 이름을 두면 한 값만 고쳐 모델이 따라옵니다.
        </p>
      )}
      <ul className="space-y-1">
        {names.map((key) => (
          <li key={key} className="flex items-center gap-1">
            <Input
              defaultValue={key}
              onBlur={(event) => rename(key, event.target.value)}
              className="h-7 flex-1 font-mono text-xs"
              aria-label={`치수 이름 ${key}`}
            />
            <Input
              type="number"
              step={0.5}
              value={String(params[key])}
              onChange={(event) => put({ ...params, [key]: Number(event.target.value) })}
              className="h-7 w-24"
              aria-label={`치수 ${key}`}
            />
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive rounded p-1"
              aria-label={`치수 ${key} 지우기`}
              onClick={() => {
                const next = { ...params }
                delete next[key]
                put(next)
              }}
            >
              <Trash2 className="size-3.5" />
            </button>
          </li>
        ))}
      </ul>
      {adding && (
        <form
          className="mt-1 flex gap-1"
          onSubmit={(event) => {
            event.preventDefault()
            const trimmed = name.trim()
            if (trimmed && !(trimmed in params)) put({ ...params, [trimmed]: 10 })
            setName('')
            setAdding(false)
          }}
        >
          <Input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="판_길이"
            className="h-7 flex-1 font-mono text-xs"
            aria-label="새 치수 이름"
          />
          <Button size="sm" type="submit" className="h-7 px-2 text-xs">
            더하기
          </Button>
        </form>
      )}
    </div>
  )
}

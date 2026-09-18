/**
 * 변수 — 값에 이름을 붙여 **한 곳만 고치면 모델이 따라오게** 한다.
 *
 * 여기 「판_길이 80」 을 두고 칸의 `fx` 를 눌러 `=판_길이` 라고 쓰면, 이 값 하나로 그것을 쓰는
 * 모든 칸이 움직인다. 스케치 구속 솔버는 없지만, 변수 + 기준 자리(`align`)로 지그가 필요로 하는
 * 「한쪽 고정, 반대쪽 늘리기」 는 된다. JSON 키는 `params` 그대로다.
 */

import { Plus, Ruler, Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'

export function ParamsPanel({ value, onChange }: { value: Recipe; onChange: (next: Recipe) => void }) {
  const params = (value.params ?? {}) as Record<string, number>
  const names = Object.keys(params)
  // **어디에 쓰였는지 세어 보여 준다.** 「변수를 만들었는데 아무 데도 안 쓴」 상태가 제일 헷갈린다 —
  // 그러면 DOE 를 돌려도 형상이 하나도 안 바뀐다.
  const recipeText = JSON.stringify(value.nodes)
  const usage = (name: string) =>
    (recipeText.match(new RegExp(`"=[^"]*(?<![\\w])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w])[^"]*"`, 'g')) ?? []).length
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [draft, setDraft] = useState('10')

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
        <span className="text-xs font-medium">변수</span>
        <span className="text-muted-foreground truncate text-[11px]">칸의 fx 로 만들거나 고른다</span>
        <Button size="sm" variant="ghost" className="ml-auto h-6 px-1" onClick={() => setAdding(true)} aria-label="변수 만들기">
          <Plus className="size-3.5" />
        </Button>
      </div>
      {names.length === 0 && !adding && (
        <p className="text-muted-foreground text-[11px]">
          없습니다. 피처(또는 스케치 도형)를 열어 바꿀 숫자 칸의 <b>fx</b> 를 누르고 <b>이름만</b> 적으면 그 값이 변수가 됩니다 — 여기 <b>+</b> 로 먼저 만들어 둘 수도 있습니다.
        </p>
      )}
      <ul className="space-y-1">
        {names.map((key) => (
          <li key={key} className="flex items-center gap-1">
            <Input
              defaultValue={key}
              onBlur={(event) => rename(key, event.target.value)}
              className="h-7 flex-1 font-mono text-xs"
              aria-label={`변수 이름 ${key}`}
            />
            <Input
              type="number"
              step={0.5}
              value={String(params[key])}
              onChange={(event) => put({ ...params, [key]: Number(event.target.value) })}
              className="h-7 w-24"
              aria-label={`변수 ${key}`}
            />
            <span
              className={`w-14 shrink-0 text-right text-[10px] ${usage(key) === 0 ? 'text-destructive' : 'text-muted-foreground'}`}
              title={usage(key) === 0 ? '아무 칸에서도 안 씁니다 — 칸의 fx 를 눌러 =이름 을 넣으세요' : `${usage(key)} 칸에서 씁니다`}
            >
              {usage(key) === 0 ? '안 쓰임' : `${usage(key)} 칸`}
            </span>
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive rounded p-1"
              aria-label={`변수 ${key} 지우기`}
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
          className="mt-1 space-y-1"
          onSubmit={(event) => {
            event.preventDefault()
            const trimmed = name.trim()
            if (trimmed && !(trimmed in params)) put({ ...params, [trimmed]: Number(draft) || 0 })
            setName('')
            setDraft('10')
            setAdding(false)
          }}
        >
          <div className="flex items-center gap-1">
            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="이름 — 예: 판_길이"
              className="h-7 flex-1 font-mono text-xs"
              aria-label="새 변수 이름"
            />
            <Input
              type="number"
              step={0.5}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="h-7 w-20"
              aria-label="새 변수 값"
            />
            <Button size="sm" type="submit" className="h-7 px-2 text-xs" disabled={!name.trim()}>
              만들기
            </Button>
            <button type="button" className="text-muted-foreground px-1 text-xs" onClick={() => setAdding(false)}>
              취소
            </button>
          </div>
          <p className="text-muted-foreground text-[10px]">
            만든 뒤 <b>피처를 열어</b> 바꿀 숫자 칸의 <b>fx</b> 를 누르고 목록에서 <code>={name.trim() || '이름'}</code> 을 고릅니다.
          </p>
        </form>
      )}
    </div>
  )
}

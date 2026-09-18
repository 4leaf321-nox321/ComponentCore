/**
 * 숫자 칸 — **변수로 바꿀 수 있는** 칸.
 *
 * `fx` 는 글자 칸을 여는 단추가 아니다. 누르면 **무엇으로 바꿀지 고르는 자리**가 열린다:
 * 이미 있는 변수를 고르거나, **지금 이 값을 그대로 새 변수로 만들거나**, 식을 직접 쓴다.
 *
 * 전에는 `=` 만 넣어 주고 말았다. 그러면 사람은 이름을 쳐 넣는데, 그 이름의 변수는 **없어서**
 * 저장할 때 「모르는 이름」 으로 막힌다. 변수를 만드는 곳이 다른 상자(왼쪽 「변수」)라는 것을
 * 아는 사람만 쓸 수 있었다 — 값을 쓰는 자리에서 바로 만들 수 있어야 한다.
 */

import { Check, Plus } from 'lucide-react'
import { useState } from 'react'

import { evalNumber, isExpression, resolvedText } from '@/modules/cad/expr'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

export function NumberField({
  value,
  onChange,
  params = {},
  onCreateParam,
  step = 0.5,
  nullable = false,
  id,
  className,
  'aria-label': ariaLabel,
}: {
  value: unknown
  onChange: (next: number | string | null) => void
  /** 지금 레시피의 변수들 — 고르는 목록이자, 식을 풀어 보여 주는 값. */
  params?: Record<string, number>
  /** 이 자리에서 변수를 만든다. 없으면 「새로 만들기」 를 감춘다. */
  onCreateParam?: (name: string, value: number) => void
  step?: number
  nullable?: boolean
  id?: string
  className?: string
  'aria-label'?: string
}) {
  const expression = isExpression(value)
  const resolved = expression ? resolvedText(value, params) : ''
  const broken = expression && !Number.isFinite(evalNumber(value, params))
  const names = Object.keys(params)
  const [open, setOpen] = useState(false)
  const [newName, setNewName] = useState('')

  /** 새 변수의 값 — 지금 칸에 있는 수. 「이 값을 변수로」 가 되려면 값이 따라가야 한다. */
  const current = expression ? (Number(resolved) || 0) : Number(value) || 0

  function use(name: string) {
    onChange(`=${name}`)
    setOpen(false)
  }

  function create() {
    const name = newName.trim()
    if (!name || !onCreateParam) return
    onCreateParam(name, current)
    onChange(`=${name}`)
    setNewName('')
    setOpen(false)
  }

  return (
    <div className="flex items-center gap-1">
      <div className="relative min-w-0 flex-1">
        {expression ? (
          <Input
            id={id}
            value={String(value)}
            onChange={(event) => onChange(event.target.value)}
            className={`h-8 pr-12 font-mono text-xs ${broken ? 'border-destructive' : ''} ${className ?? ''}`}
            placeholder="=두께 * 2"
            aria-label={ariaLabel}
          />
        ) : (
          <Input
            id={id}
            type="number"
            step={step}
            value={value === null || value === undefined || value === '' ? '' : String(value)}
            onChange={(event) => {
              const raw = event.target.value
              if (raw === '') onChange(nullable ? null : 0)
              else onChange(Number(raw))
            }}
            className={`h-8 ${className ?? ''}`}
            aria-label={ariaLabel}
          />
        )}
        {expression && (
          <span
            className={`pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 font-mono text-[10px] ${broken ? 'text-destructive' : 'text-muted-foreground'}`}
            title={broken ? '이 식을 풀 수 없습니다 — 없는 변수 이름일 수 있습니다' : '지금 값'}
          >
            {broken ? '?' : resolved}
          </span>
        )}
      </div>

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={ariaLabel ? `${ariaLabel} 변수로` : '변수로'}
            title="변수로 — 고르거나 이 값을 새 변수로 만듭니다"
            className={`h-8 shrink-0 rounded-md border px-2 font-mono text-xs ${expression ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
          >
            fx
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-64 p-2" align="end">
          <p className="text-muted-foreground mb-1 text-[11px]">이 칸을 무엇으로 할까요</p>

          {names.length > 0 && (
            <ul className="mb-2 max-h-40 space-y-0.5 overflow-y-auto">
              {names.map((name) => (
                <li key={name}>
                  <button
                    type="button"
                    onClick={() => use(name)}
                    className="hover:bg-accent flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs"
                  >
                    <span className="font-mono">={name}</span>
                    <span className="text-muted-foreground ml-auto font-mono text-[10px]">{params[name]}</span>
                    {value === `=${name}` && <Check className="size-3" />}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {onCreateParam && (
            <div className="space-y-1 border-t pt-2">
              <p className="text-[11px]">
                이 값(<span className="font-mono">{current}</span>)을 새 변수로
              </p>
              <div className="flex items-center gap-1">
                <Input
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      create()
                    }
                  }}
                  placeholder="이름 — 예: 두께"
                  className="h-7 flex-1 font-mono text-xs"
                  aria-label="새 변수 이름"
                />
                <Button size="sm" className="h-7 px-2 text-xs" disabled={!newName.trim() || newName.trim() in params} onClick={create}>
                  <Plus className="size-3" /> 만들기
                </Button>
              </div>
              {newName.trim() in params && <p className="text-destructive text-[10px]">이미 있는 이름입니다 — 위에서 고르세요.</p>}
            </div>
          )}

          <div className="mt-2 flex gap-2 border-t pt-2 text-[11px]">
            <button type="button" className="hover:underline" onClick={() => { onChange('='); setOpen(false) }}>
              식 직접 쓰기
            </button>
            {expression && (
              <button
                type="button"
                className="text-muted-foreground ml-auto hover:underline"
                onClick={() => { onChange(Number(resolved) || 0); setOpen(false) }}
              >
                숫자로 되돌리기
              </button>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

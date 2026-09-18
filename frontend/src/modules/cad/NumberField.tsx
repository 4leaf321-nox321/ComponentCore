/**
 * 숫자 칸 — **변수로 바꿀 수 있는** 칸.
 *
 * `fx` 를 누르면 글자 칸이 되고 `=두께 * 2` 처럼 쓴다. 옆에 **풀린 값**을 같이 보여 준다 —
 * 식만 보이면 자기가 무엇을 적었는지 확인할 방법이 없다(서버가 풀어 줄 때까지 기다려야 한다).
 *
 * 피처 폼과 스케치 캔버스가 같은 칸을 쓴다. 한쪽에만 있으면 「그림은 변수화가 안 되네」 가 된다.
 */

import { evalNumber, isExpression, resolvedText } from '@/modules/cad/expr'
import { Input } from '@/shared/components/ui/input'

export function NumberField({
  value,
  onChange,
  params = {},
  step = 0.5,
  nullable = false,
  id,
  className,
  'aria-label': ariaLabel,
}: {
  value: unknown
  onChange: (next: number | string | null) => void
  /** 지금 레시피의 변수들 — 식을 풀어 보여 주는 데 쓴다. */
  params?: Record<string, number>
  step?: number
  nullable?: boolean
  id?: string
  className?: string
  'aria-label'?: string
}) {
  const expression = isExpression(value)
  const resolved = expression ? resolvedText(value, params) : ''
  const broken = expression && !Number.isFinite(evalNumber(value, params))
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
            title={broken ? '이 식을 풀 수 없습니다 — 변수 이름을 확인하세요' : '지금 값'}
          >
            {broken ? '?' : resolved}
          </span>
        )}
      </div>
      <button
        type="button"
        aria-label={expression ? '숫자로' : '변수로'}
        title={expression ? '숫자로 되돌리기' : '변수로 — 「=두께 * 2」 처럼 씁니다'}
        onClick={() => onChange(expression ? (Number(resolved) || 0) : '=')}
        className={`h-8 shrink-0 rounded-md border px-2 font-mono text-xs ${expression ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'}`}
      >
        fx
      </button>
    </div>
  )
}

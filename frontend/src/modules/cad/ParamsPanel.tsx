/**
 * 변수 — 값에 이름을 붙여 **한 곳만 고치면 모델이 따라오게** 한다.
 *
 * 여기 「판_길이 80」 을 두고 칸의 `fx` 를 눌러 `=판_길이` 라고 쓰면, 이 값 하나로 그것을 쓰는
 * 모든 칸이 움직인다. 스케치 구속 솔버는 없지만, 변수 + 기준 자리(`align`)로 지그가 필요로 하는
 * 「한쪽 고정, 반대쪽 늘리기」 는 된다. JSON 키는 `params` 그대로다.
 *
 * 값이 `=식` 인 변수(`지지_간격 = 간격비 * 두께`)는 식 그대로 보이고 고친다 — 숫자 칸에 넣으면
 * 빈칸으로 보이고, 숫자를 치는 순간 식이 지워졌다. 쓰인 곳은 입력란 · 다른 변수 · 해석 조건을 다
 * 센다(`paramUsage.ts`) — 조건이나 다른 변수가 쓰는 변수는 지우지 못하고, 조건이 쓰는 변수는 이름도
 * 못 바꾼다(조건은 이 화면이 고치지 않는다).
 *
 * 「치수 표시」 를 켜면 변수마다 형상 위의 치수가 3D 에 그어진다(`paramDims.ts`, 그리는 것은
 * 편집기의 뷰어). 행에 마우스를 올리면 그 변수만 남는다. 3D 에 그릴 것이 없는 변수(형상에 안
 * 쓰는 변수 · 값과 같은 치수가 없는 변수)는 행 아래에 그렇다고 적는다.
 */

import { Plus, Ruler, Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { dimNote } from '@/modules/cad/paramDims'
import type { ParamDimsState } from '@/modules/cad/paramDims'
import { namePattern, paramUses, useLabel, useTitle } from '@/modules/cad/paramUsage'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'

/** 「치수 표시」 — 켬 · 끔과 서버의 답, 그 치수만 남길 변수. 편집기가 쥐고 뷰어에 그린다. */
export interface ParamsDims {
  on: boolean
  onToggle: (next: boolean) => void
  state: ParamDimsState
  focus: string | null
  onFocus: (name: string | null) => void
}

export function ParamsPanel({
  value,
  onChange,
  conditions,
  dims,
}: {
  value: Recipe
  onChange: (next: Recipe) => void
  /** 이 도면의 해석 조건 — 주면 조건이 쓰는 변수도 「쓰임」 으로 센다. */
  conditions?: unknown
  /** 주면 「치수 표시」 단추가 생긴다. */
  dims?: ParamsDims
}) {
  const params = (value.params ?? {}) as Record<string, number | string>
  const names = Object.keys(params)
  // **어디에 쓰였는지 세어 보여 준다.** 「변수를 만들었는데 아무 데도 안 쓴」 상태가 제일 헷갈린다 —
  // 그러면 DOE 를 돌려도 형상이 하나도 안 바뀐다.
  const uses = paramUses(value, conditions)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [draft, setDraft] = useState('10')

  function put(next: Record<string, number | string>) {
    onChange({ ...value, params: next })
  }

  function rename(from: string, to: string) {
    const trimmed = to.trim()
    if (!trimmed || trimmed === from || trimmed in params) return
    // 이름을 바꾸면 그것을 쓰던 식도 따라 바꾼다 — 입력란과 다른 변수의 식. 안 그러면 레시피가 통째로
    // 깨진다.
    const pattern = namePattern(from)
    const swap = (text: string) => text.replaceAll(/"=[^"]*"/g, (found) => found.replaceAll(pattern, trimmed))
    const swapped = JSON.parse(swap(JSON.stringify(value.nodes))) as Recipe['nodes']
    const next: Record<string, number | string> = {}
    for (const key of names) {
      const old = params[key]
      next[key === from ? trimmed : key] = typeof old === 'string' ? old.replaceAll(pattern, trimmed) : old
    }
    onChange({ ...value, params: next, nodes: swapped })
  }

  return (
    <div className="mb-2 rounded-md border p-2">
      <div className="mb-1 flex items-center gap-1">
        <Ruler className="text-muted-foreground size-3.5" />
        <span className="shrink-0 text-xs font-medium whitespace-nowrap">변수</span>
        <span className="text-muted-foreground min-w-0 truncate text-[11px]">입력란의 fx로 생성하거나 선택합니다.</span>
        {dims && names.length > 0 && (
          <Button
            size="sm"
            variant={dims.on ? 'secondary' : 'ghost'}
            className="ml-auto h-6 shrink-0 px-1.5 text-[11px]"
            onClick={() => dims.onToggle(!dims.on)}
            aria-pressed={dims.on}
            title="변수마다 해당 치수를 3D에 표시합니다. 행에 마우스를 올리면 해당 치수를 강조합니다."
          >
            치수 표시
          </Button>
        )}
        <Button size="sm" variant="ghost" className={`${dims && names.length > 0 ? '' : 'ml-auto'} h-6 px-1`} onClick={() => setAdding(true)} aria-label="변수 생성">
          <Plus className="size-3.5" />
        </Button>
      </div>
      {names.length === 0 && !adding && (
        <p className="text-muted-foreground text-[11px]">
          변수가 없습니다. 피처(또는 스케치 도형)를 열고 변경할 숫자 입력란의 <b>fx</b>를 누른 뒤 <b>이름</b>을 입력하면 해당 값이 변수가 됩니다. 이곳의 <b>+</b>로 미리 생성할 수도 있습니다.
        </p>
      )}
      {dims?.on && dims.state.loading && (
        <p className="text-muted-foreground mb-1 text-[11px]" role="status">
          치수 위치 계산 중…
        </p>
      )}
      {dims?.on && dims.state.error && (
        <p className="text-destructive mb-1 text-[11px]" role="alert">
          치수 위치를 찾지 못했습니다: {dims.state.error.message}
        </p>
      )}
      <ul className="space-y-1">
        {names.map((key) => {
          const found = dims?.on ? dims.state.data?.dims.find((one) => one.name === key) : undefined
          return (
          <li
            key={key}
            onMouseEnter={dims?.on ? () => dims.onFocus(key) : undefined}
            onMouseLeave={dims?.on ? () => dims.onFocus(null) : undefined}
            className={`rounded ${dims?.on && dims.focus === key ? 'bg-accent/60' : ''}`}
          >
          <div className="flex items-center gap-1">
            <Input
              defaultValue={key}
              readOnly={uses[key].conditions > 0}
              title={uses[key].conditions > 0 ? '해석 조건에서 사용 중이므로 이름을 바꿀 수 없습니다.' : undefined}
              onBlur={(event) => rename(key, event.target.value)}
              className="h-7 flex-1 font-mono text-xs"
              aria-label={`변수 이름 ${key}`}
            />
            {typeof params[key] === 'string' ? (
              <Input
                value={String(params[key])}
                onChange={(event) => {
                  const text = event.target.value
                  const number = Number(text)
                  put({ ...params, [key]: !text.startsWith('=') && text.trim() !== '' && Number.isFinite(number) ? number : text })
                }}
                className="h-7 w-36 font-mono text-xs"
                title="다른 변수로 정의된 식입니다. 숫자를 입력하면 고정 값이 됩니다."
                aria-label={`변수 ${key}`}
              />
            ) : (
              <Input
                type="number"
                step={0.5}
                value={String(params[key])}
                onChange={(event) => put({ ...params, [key]: Number(event.target.value) })}
                className="h-7 w-24"
                aria-label={`변수 ${key}`}
              />
            )}
            <span
              className={`w-20 shrink-0 text-right text-[10px] ${useLabel(uses[key]) === '미사용' ? 'text-destructive' : 'text-muted-foreground'}`}
              title={useTitle(uses[key])}
            >
              {useLabel(uses[key])}
            </span>
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive rounded p-1 disabled:opacity-40"
              aria-label={`변수 ${key} 삭제`}
              disabled={uses[key].params.length > 0 || uses[key].conditions > 0}
              title={uses[key].params.length > 0 || uses[key].conditions > 0 ? '다른 변수의 식이나 해석 조건에서 사용 중이므로 삭제할 수 없습니다.' : undefined}
              onClick={() => {
                const next = { ...params }
                delete next[key]
                put(next)
              }}
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
          {/* 3D 에 그을 것이 없는 변수는 까닭을 적는다 — 안 보이면 고장 난 줄 안다. */}
          {found && found.status !== 'dimension' && (
            <p
              className={`truncate px-1 text-[10px] ${found.status === 'moved' ? 'text-amber-700 dark:text-amber-400' : 'text-muted-foreground'}`}
              title={found.message ?? undefined}
            >
              {dimNote(found)}
            </p>
          )}
          </li>
          )
        })}
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
              placeholder="이름(예: 판_길이)"
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
              생성
            </Button>
            <button type="button" className="text-muted-foreground px-1 text-xs" onClick={() => setAdding(false)}>
              취소
            </button>
          </div>
          <p className="text-muted-foreground text-[10px]">
            생성한 뒤 <b>피처를 열고</b> 변경할 숫자 입력란의 <b>fx</b>를 눌러 목록에서 <code>={name.trim() || '이름'}</code>을(를) 선택하십시오.
          </p>
        </form>
      )}
    </div>
  )
}
